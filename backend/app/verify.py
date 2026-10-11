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
    "firebase_open_read",    # Firebase RTDB node readable without auth -> a real finding
    "cross_tenant_access",   # authenticated user saw another tenant's rows -> a real finding
    "tenant_isolated",       # authenticated user saw only their own tenant -> no finding
    "unauthenticated_endpoint_data",  # generic endpoint returned data to anon -> CANDIDATE
    "endpoint_requires_auth",          # generic endpoint required auth -> no finding
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


def verify_tenant_isolation(result: ToolResult) -> Verdict:
    """Classify an authenticated cross-tenant isolation check (Check C)."""
    if not result.ok:
        cat = result.error_category or "tool_failure"
        if cat == "network_error":
            return Verdict("network_error", "could not reach the endpoint", False)
        return Verdict("tool_failure", f"tool failed: {result.signal.get('error')}", False)

    status = result.signal.get("http_status")
    pg_error = result.signal.get("pg_error_code")
    if status in (401, 403) or pg_error is not None:
        return Verdict("access_denied", f"backend denied the authenticated read (HTTP {status})", False)
    if status == 200 and result.signal.get("is_list"):
        foreign = result.signal.get("foreign_tenants", 0)
        if foreign and foreign > 0:
            return Verdict(
                "cross_tenant_access",
                f"authenticated user saw rows from {foreign} other tenant(s) — isolation failure",
                True,
            )
        return Verdict("tenant_isolated",
                       "authenticated user saw only their own tenant's rows", False)
    return Verdict("inconclusive", f"unclassified response (HTTP {status})", False)


def verify_firebase_read(result: ToolResult) -> Verdict:
    """Classify a Firebase RTDB anonymous-read check."""
    if not result.ok:
        cat = result.error_category or "tool_failure"
        if cat == "network_error":
            return Verdict("network_error", "could not reach the database", False)
        return Verdict("tool_failure", f"tool failed: {result.signal.get('error')}", False)
    if result.signal.get("denied"):
        return Verdict("access_denied",
                       f"database denied anonymous read (HTTP {result.signal.get('http_status')})",
                       False)
    if result.signal.get("has_data"):
        return Verdict("firebase_open_read",
                       "Firebase Realtime Database returned data to an unauthenticated request "
                       "— read rules are open", True)
    return Verdict("empty", "reachable but returned no data — inconclusive", False)


def verify_unauthenticated_endpoint(result: ToolResult) -> Verdict:
    """Classify a generic unauthenticated-endpoint probe. A 200 with data is a CANDIDATE
    (we cannot know it should be private); auth-required is a clean negative."""
    if not result.ok:
        cat = result.error_category or "tool_failure"
        if cat == "network_error":
            return Verdict("network_error", "could not reach the endpoint", False)
        return Verdict("tool_failure", f"tool failed: {result.signal.get('error')}", False)
    status = result.signal.get("http_status")
    if status in (401, 403):
        return Verdict("endpoint_requires_auth",
                       f"endpoint required authentication (HTTP {status})", False)
    if status == 200 and result.signal.get("has_payload"):
        # is_finding=True but the loop records this as a CANDIDATE, not confirmed.
        return Verdict("unauthenticated_endpoint_data",
                       "endpoint returned structured data to an unauthenticated request — "
                       "CANDIDATE; may be intentionally public, needs human review", True)
    return Verdict("inconclusive", f"no clear data exposure (HTTP {status})", False)
