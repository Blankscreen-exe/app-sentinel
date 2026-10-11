"""Sandbox Procrastinate app and the analysis task.

This worker is bound to sandbox-db only and runs on the isolated network. It cannot
reach the main database or the internet. It reads APKs from shared storage, analyzes
them, and writes the raw result into sandbox-db for the orchestrator to collect
(outbox pattern, ADR-005).
"""

from __future__ import annotations

import json
import logging
import os

import psycopg
from procrastinate import App, PsycopgConnector

from analyzer import analyze

logging.basicConfig(level=logging.INFO, format='{"logger":"sandbox","message":"%(message)s"}')
logger = logging.getLogger("sandbox")

# androguard logs very verbosely via loguru; silence it to keep our logs clean.
try:
    from loguru import logger as _loguru

    _loguru.remove()
except Exception:  # noqa: BLE001
    pass

SANDBOX_DB = os.environ["SANDBOX_DATABASE_URL"]
DATA_DIR = os.environ.get("DATA_DIR", "/data")

app = App(connector=PsycopgConnector(conninfo=SANDBOX_DB))


def _already_done(artifact_id: str) -> bool:
    with psycopg.connect(SANDBOX_DB) as conn:
        row = conn.execute(
            "SELECT 1 FROM sandbox_result WHERE artifact_id = %s", (artifact_id,)
        ).fetchone()
    return row is not None


def _write_result(artifact_id: str, sha256: str, status: str, payload: dict | None, error: str | None) -> None:
    with psycopg.connect(SANDBOX_DB) as conn:
        conn.execute(
            """
            INSERT INTO sandbox_result (artifact_id, sha256, status, payload, error)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (artifact_id) DO NOTHING
            """,
            (artifact_id, sha256, status, json.dumps(payload) if payload else None, error),
        )
        conn.commit()


@app.task(name="run_static_analysis", queue="analysis")
def run_static_analysis(artifact_id: str, storage_key: str, sha256: str) -> None:
    # Idempotent: a retried job must not duplicate work.
    if _already_done(artifact_id):
        logger.info(f"result already present for {artifact_id}, skipping")
        return

    apk_path = os.path.join(DATA_DIR, storage_key)
    if not os.path.isfile(apk_path):
        _write_result(artifact_id, sha256, "error", None, f"artifact file missing: {storage_key}")
        return

    try:
        payload = analyze(apk_path)
        _write_result(artifact_id, sha256, "done", payload, None)
        logger.info(f"analysis done for {artifact_id}")
    except Exception as exc:  # noqa: BLE001 - record failure, do not crash the queue
        _write_result(artifact_id, sha256, "error", None, f"{type(exc).__name__}: {exc}")
        logger.info(f"analysis error for {artifact_id}: {exc}")
