"""Orchestrator side of the sandbox boundary (ADR-005).

The main worker can reach sandbox-db (it is the only service on both networks). It
enqueues the analysis job into the sandbox queue and later reads the raw result row.
It does NOT import the sandbox's analysis code; it only speaks to sandbox-db.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import psycopg
from procrastinate import App, PsycopgConnector

from app.config import get_settings

# Built lazily: the API process imports this module but has no SANDBOX_DATABASE_URL.
# Only the worker, which does, ever calls the functions below.
_sandbox_app: App | None = None


def _sandbox_dsn() -> str:
    dsn = get_settings().sandbox_database_url
    if not dsn:
        raise RuntimeError("SANDBOX_DATABASE_URL is not configured")
    return dsn


def _get_sandbox_app() -> App:
    global _sandbox_app
    if _sandbox_app is None:
        _sandbox_app = App(connector=PsycopgConnector(conninfo=_sandbox_dsn()))
    return _sandbox_app


def enqueue_analysis(artifact_id: str, storage_key: str, sha256: str) -> None:
    """Idempotently enqueue a sandbox analysis job.

    A queueing lock keyed by artifact id prevents a duplicate job from being queued
    while one is already pending (idempotent handoff).
    """
    sandbox_app = _get_sandbox_app()
    with sandbox_app.open():
        sandbox_app.configure_task(
            name="run_static_analysis",
            queue="analysis",
            queueing_lock=f"analysis:{artifact_id}",
        ).defer(artifact_id=artifact_id, storage_key=storage_key, sha256=sha256)


@dataclass
class SandboxResult:
    status: str  # done | error
    sha256: str
    payload: dict[str, Any] | None
    error: str | None


def read_result(artifact_id: str) -> SandboxResult | None:
    """Return the raw sandbox result for an artifact, or None if not ready yet."""
    with psycopg.connect(_sandbox_dsn()) as conn:
        row = conn.execute(
            "SELECT status, sha256, payload, error FROM sandbox_result WHERE artifact_id = %s",
            (artifact_id,),
        ).fetchone()
    if row is None:
        return None
    status, sha256, payload, error = row
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    return SandboxResult(status=status, sha256=sha256, payload=payload, error=error)
