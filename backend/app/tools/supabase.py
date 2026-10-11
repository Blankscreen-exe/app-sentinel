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
