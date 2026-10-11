"""Independent verification of tool results.

The verifier interprets the *actual* tool signal with deterministic rules. The LLM's
assertion that a test succeeded is never the proof — this is. For an anonymous read it
distinguishes: unauthorized access, authorized-public access, denial, empty, network
error, tool failure, inconclusive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.tools.base import ToolResult

Outcome = Literal[
    "unauthorized_access",   # anon got rows that should be restricted -> a real finding
    "access_denied",         # backend refused (401/403/empty due to RLS) -> no finding
    "empty",                 # reachable, authorized, but no rows -> inconclusive
    "network_error",
    "tool_failure",
    "inconclusive",
]


@dataclass
class Verdict:
    outcome: Outcome
    rationale: str
    is_finding: bool


def verify_anonymous_read(result: ToolResult) -> Verdict:
    """Classify an anonymous-read result deterministically."""
    if not result.ok:
        cat = result.error_category or "tool_failure"
        if cat == "network_error":
            return Verdict("network_error", "could not reach the endpoint", False)
        return Verdict("tool_failure", f"tool failed: {result.signal.get('error')}", False)

    status = result.signal.get("http_status")
    row_count = result.signal.get("row_count")
    pg_error = result.signal.get("pg_error_code")
    is_list = result.signal.get("is_list")

    # Explicit denial by the backend.
    if status in (401, 403):
        return Verdict("access_denied", f"backend denied anonymous access (HTTP {status})", False)
    if pg_error is not None:
        return Verdict("access_denied", f"backend returned error code {pg_error}", False)

    # A successful list response is the decisive signal.
    if status == 200 and is_list:
        if row_count and row_count > 0:
            return Verdict(
                "unauthorized_access",
                f"anonymous request returned {row_count} row(s) from a resource expected "
                "to be restricted",
                True,
            )
        return Verdict(
            "empty",
            "anonymous request was accepted but returned no rows (RLS may deny, or table is "
            "empty) — inconclusive",
            False,
        )

    return Verdict("inconclusive", f"unclassified response (HTTP {status})", False)
