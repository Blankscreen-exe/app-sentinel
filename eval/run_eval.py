#!/usr/bin/env python3
"""Evaluation harness: precision/recall against the known-answer lab.

Ground truth (which anonymous reads SHOULD be flagged):
  broken : trips=vuln, invoices=vuln, profiles=safe, receipts=safe (no such table)
  correct: all safe

For each mode, switches the lab, runs one comprehensive assessment (via
backend/eval/assess_lab.py in the worker), compares flagged tables to ground truth, and
reports TP/FP/FN/TN, precision, recall, false-positive rate.

Run from the repo root (lab + stack up, worker connected to the lab network):
    python3 eval/run_eval.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ["trips", "invoices", "profiles", "receipts"]

GROUND_TRUTH = {
    "broken": {"trips": True, "invoices": True, "profiles": False, "receipts": False},
    "correct": {"trips": False, "invoices": False, "profiles": False, "receipts": False},
}


def _sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def _anon_key() -> str:
    return _sh(["python3", "lab/mint_anon_key.py"]).stdout.strip()


def _set_mode(mode: str) -> None:
    _sh(["bash", "lab/mode.sh", mode])


def _run_mode(anon_key: str) -> list[str]:
    out = _sh([
        "docker", "compose", "exec", "-T", "worker",
        "python", "eval/assess_lab.py", anon_key,
    ]).stdout.strip().splitlines()
    # The last JSON line is our result.
    for line in reversed(out):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)["flagged"]
    return []


def _metrics(confusion: dict[str, int]) -> dict[str, float]:
    tp, fp, fn, tn = (confusion[k] for k in ("tp", "fp", "fn", "tn"))
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "false_positive_rate": fpr, "f1": f1}


def main() -> None:
    anon_key = _anon_key()
    confusion = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    print("Evaluation against the known-answer lab\n" + "=" * 42)
    for mode, truth in GROUND_TRUTH.items():
        _set_mode(mode)
        flagged = set(_run_mode(anon_key))
        print(f"\n[{mode}] flagged = {sorted(flagged) or '(none)'}")
        for table, is_vuln in truth.items():
            predicted = table in flagged
            if is_vuln and predicted:
                confusion["tp"] += 1; mark = "TP ✓"
            elif is_vuln and not predicted:
                confusion["fn"] += 1; mark = "FN ✗ (missed)"
            elif not is_vuln and predicted:
                confusion["fp"] += 1; mark = "FP ✗ (false alarm)"
            else:
                confusion["tn"] += 1; mark = "TN ✓"
            print(f"    {table:9} expected={'vuln' if is_vuln else 'safe':4} "
                  f"predicted={'vuln' if predicted else 'safe':4}  {mark}")

    m = _metrics(confusion)
    print("\n" + "=" * 42)
    print(f"confusion: {confusion}")
    print(f"precision: {m['precision']:.2f}  recall: {m['recall']:.2f}  "
          f"FPR: {m['false_positive_rate']:.2f}  F1: {m['f1']:.2f}")
    ok = confusion["fp"] == 0 and confusion["fn"] == 0
    print("RESULT:", "perfect (no false alarms, no misses)" if ok else "see confusion above")


if __name__ == "__main__":
    main()
