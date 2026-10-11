# Evaluation

Measures the assessment pipeline against the **known-answer lab** — the honest way to
judge a security tool (not by how many alarms it raises, but by whether it's right).

## Run

Stack + lab up, worker connected to the lab network:

```bash
bash lab/connect-worker.sh
python3 eval/run_eval.py
```

## What it does

For each lab mode it switches the lab, runs one comprehensive assessment (tests every
candidate table via a deterministic planner, so results are repeatable), and compares the
flagged tables to ground truth:

| table | broken | correct |
|---|---|---|
| trips | vuln | safe |
| invoices | vuln | safe |
| profiles | safe | safe |
| receipts | safe (no such table) | safe |

It reports TP / FP / FN / TN, precision, recall, false-positive rate, and F1.

## Latest result

`precision 1.00 · recall 1.00 · FPR 0.00 · F1 1.00` (2 TP, 6 TN, 0 FP, 0 FN).

**Honest caveat:** this validates the control plane (tools + verifier + gate) on a small
known-answer set — 4 tables × 2 modes. It is not a claim of general accuracy on arbitrary
apps/backends. The deterministic planner guarantees full coverage so the metric isolates
detection correctness from the LLM's step choices; a separate run with the real planner
confirmed the same findings on broken mode.
