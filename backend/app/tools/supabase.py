"""Supabase assessment tools.

- classify_client_key: offline classification of a discovered key (no network).
- test_scoped_anonymous_read: a minimal, read-only, anonymous request to ONE approved
  table, data-minimized (tiny row cap, no bulk retrieval). It records the raw signal;
  the verifier decides what it means.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.scope.config import ScopeConfig
from app.scope.gate import Resolver, default_resolver
from app.tools.base import ToolResult
from app.tools.http import safe_get

# How many rows we ever request to demonstrate access — data minimization (ADR, §12.3).
_ANON_READ_LIMIT = 2


def classify_client_key(key: str) -> dict[str, Any]:
    """Classify a discovered key by its format. Offline, deterministic."""
    k = key.strip()
    if k.startswith("sb_publishable_"):
        return {"classification": "public_client_key", "sensitive": False,
                "note": "Supabase publishable key — designed to ship in clients; not a secret."}
    if k.startswith("sb_secret_"):
        return {"classification": "secret_key", "sensitive": True,
                "note": "Supabase secret key — must never ship in a client."}
    if k.startswith("eyJ"):
        return {"classification": "jwt", "sensitive": None,
                "note": "JWT-form key; role (anon vs service_role) must be decoded to classify."}
    return {"classification": "unknown", "sensitive": None, "note": "unrecognized key format"}


@dataclass
class AnonReadArgs:
    base_url: str          # e.g. http://lab-rest:3000
    table: str             # single approved table
    anon_key: str          # the client/anon key to present
    columns: str = "*"     # PostgREST select


def test_scoped_anonymous_read(
    args: AnonReadArgs,
    scope: ScopeConfig,
    *,
    resolver: Resolver = default_resolver,
) -> ToolResult:
    """Minimal anonymous read of one approved table. Records status + row count + sample."""
    url = f"{args.base_url.rstrip('/')}/{args.table}?select={args.columns}&limit={_ANON_READ_LIMIT}"
    headers = {"apikey": args.anon_key, "Authorization": f"Bearer {args.anon_key}"}

    out = safe_get(url, scope, headers=headers, resolver=resolver)
    if not out.ok:
        category = "network_error" if (out.error or "").startswith("network") else "tool_failure"
        return ToolResult(
            ok=False, tool="test_scoped_anonymous_read",
            error_category=category, signal={"error": out.error},
        )

    row_count: int | None = None
    sample_shape: list[str] = []
    parsed: Any = None
    try:
        parsed = json.loads(out.body_text or "")
        if isinstance(parsed, list):
            row_count = len(parsed)
            if parsed and isinstance(parsed[0], dict):
                sample_shape = sorted(parsed[0].keys())
    except json.JSONDecodeError:
        parsed = None

    # PostgREST returns an {code,message,...} object on errors (e.g. permission denied).
    pg_error = parsed.get("code") if isinstance(parsed, dict) else None

    return ToolResult(
        ok=True,
        tool="test_scoped_anonymous_read",
        signal={
            "http_status": out.status,
            "row_count": row_count,
            "pg_error_code": pg_error,
            "is_list": isinstance(parsed, list),
        },
        # Evidence is minimal: status, count, and the column names only — not the row data.
        evidence={
            "request": {"table": args.table, "limit": _ANON_READ_LIMIT, "anonymous": True},
            "response_status": out.status,
            "row_count": row_count,
            "sample_columns": sample_shape,
        },
    )


@dataclass
class AuthReadArgs:
    base_url: str
    table: str
    user_jwt: str          # an authenticated test account's JWT
    own_tenant_id: str     # the tenant the test account belongs to


def test_authenticated_tenant_isolation(
    args: AuthReadArgs,
    scope: ScopeConfig,
    *,
    resolver: Resolver = default_resolver,
) -> ToolResult:
    """Check C: as an authenticated test user, read a table and see whether rows from
    OTHER tenants are returned (a cross-tenant isolation failure). Minimal: only the
    tenant_id column is read."""
    url = f"{args.base_url.rstrip('/')}/{args.table}?select=tenant_id&limit=10"
    headers = {"apikey": args.user_jwt, "Authorization": f"Bearer {args.user_jwt}"}
    out = safe_get(url, scope, headers=headers, resolver=resolver)
    if not out.ok:
        category = "network_error" if (out.error or "").startswith("network") else "tool_failure"
        return ToolResult(ok=False, tool="test_authenticated_tenant_isolation",
                          error_category=category, signal={"error": out.error})

    parsed: Any = None
    try:
        parsed = json.loads(out.body_text or "")
    except json.JSONDecodeError:
        parsed = None
    pg_error = parsed.get("code") if isinstance(parsed, dict) else None
    tenants: list[str] = []
    if isinstance(parsed, list):
        tenants = sorted({str(r.get("tenant_id")) for r in parsed if isinstance(r, dict)})
    foreign = [t for t in tenants if t and t != args.own_tenant_id]
    return ToolResult(
        ok=True, tool="test_authenticated_tenant_isolation",
        signal={"http_status": out.status, "pg_error_code": pg_error,
                "is_list": isinstance(parsed, list), "foreign_tenants": len(foreign)},
        evidence={"request": {"table": args.table, "as_tenant": args.own_tenant_id,
                              "authenticated": True},
                  "response_status": out.status, "tenants_seen": tenants,
                  "foreign_tenants_seen": foreign},
    )


def review_rls_configuration(admin_dsn: str, tables: list[str]) -> ToolResult:
    """Check D: with authorized admin DB access, review RLS posture per table (metadata
    only — reads pg_class.relrowsecurity and pg_policies). Not an exploit; a config review."""
    import psycopg  # local import; only used when admin access is authorized

    try:
        rows: dict[str, Any] = {}
        with psycopg.connect(admin_dsn, connect_timeout=5) as conn:
            for t in tables:
                enabled = conn.execute(
                    "SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(%s)", (f"public.{t}",)
                ).fetchone()
                pols = conn.execute(
                    "SELECT polname FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid "
                    "WHERE c.oid = to_regclass(%s)", (f"public.{t}",)
                ).fetchall()
                rows[t] = {
                    "rls_enabled": bool(enabled[0]) if enabled else None,
                    "policy_count": len(pols),
                }
        return ToolResult(ok=True, tool="review_rls_configuration",
                          signal={"tables_reviewed": len(rows)}, evidence={"rls": rows})
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, tool="review_rls_configuration",
                          error_category="tool_failure", signal={"error": str(exc)[:200]})


@dataclass
class FirebaseReadArgs:
    base_url: str          # e.g. https://proj.firebaseio.com  (or the lab mock)
    path: str = "/"        # RTDB node path to probe


def test_firebase_rtdb_read(
    args: FirebaseReadArgs,
    scope: ScopeConfig,
    *,
    resolver: Resolver = default_resolver,
) -> ToolResult:
    """Check whether a Firebase Realtime Database node is readable without authentication,
    using the real RTDB REST contract: GET <base>/<path>.json. Minimal, read-only."""
    node = args.path.strip("/")
    suffix = f"/{node}.json" if node else "/.json"
    url = f"{args.base_url.rstrip('/')}{suffix}?shallow=true"
    out = safe_get(url, scope, resolver=resolver)
    if not out.ok:
        category = "network_error" if (out.error or "").startswith("network") else "tool_failure"
        return ToolResult(ok=False, tool="test_firebase_rtdb_read",
                          error_category=category, signal={"error": out.error})

    parsed: Any = None
    try:
        parsed = json.loads(out.body_text or "null")
    except json.JSONDecodeError:
        parsed = None
    # RTDB denies with HTTP 401/403 and {"error": "Permission denied"}. Only treat a
    # permission error as "denied" — a 404/other error is not evidence of locked rules.
    err = parsed.get("error") if isinstance(parsed, dict) else None
    denied = out.status in (401, 403) or (err is not None and "permission" in str(err).lower())
    has_data = parsed is not None and not (isinstance(parsed, dict) and "error" in parsed)
    keys = sorted(parsed.keys()) if isinstance(parsed, dict) and "error" not in parsed else []
    return ToolResult(
        ok=True, tool="test_firebase_rtdb_read",
        signal={"http_status": out.status, "denied": denied, "has_data": has_data},
        evidence={"request": {"path": args.path, "anonymous": True, "shallow": True},
                  "response_status": out.status, "top_level_keys": keys},
    )


@dataclass
class RestProbeArgs:
    url: str               # a discovered endpoint URL to probe unauthenticated


def test_unauthenticated_endpoint(
    args: RestProbeArgs,
    scope: ScopeConfig,
    *,
    resolver: Resolver = default_resolver,
) -> ToolResult:
    """Generic check: does an endpoint return structured data to an unauthenticated GET?
    A 200 cannot prove the data *should* be private, so the verifier treats a hit as a
    CANDIDATE for human review, never a confirmed vulnerability."""
    out = safe_get(args.url, scope, resolver=resolver)
    if not out.ok:
        category = "network_error" if (out.error or "").startswith("network") else "tool_failure"
        return ToolResult(ok=False, tool="test_unauthenticated_endpoint",
                          error_category=category, signal={"error": out.error})
    body = out.body_text or ""
    parsed: Any = None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None
    is_json = parsed is not None
    has_payload = (isinstance(parsed, list) and len(parsed) > 0) or (
        isinstance(parsed, dict) and bool(parsed) and "error" not in parsed
    )
    return ToolResult(
        ok=True, tool="test_unauthenticated_endpoint",
        signal={"http_status": out.status, "is_json": is_json, "has_payload": has_payload},
        evidence={"request": {"url": args.url, "anonymous": True},
                  "response_status": out.status, "json": is_json, "bytes": len(body)},
    )
