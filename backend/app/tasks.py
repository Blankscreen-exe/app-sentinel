"""Main-queue orchestration tasks (run in the main worker).

The analysis task implements the orchestrator side of the outbox handoff: enqueue the
sandbox job, wait for the result in sandbox-db, then validate and persist it into
main-db. The sandbox never writes to main-db; only this trusted code does.
"""

from __future__ import annotations

import logging
import time

from app.analysis.ingest import ingest
from app.config import get_settings
from app.db import SessionLocal
from app.logging_setup import new_trace_id
from app.models import ApplicationArtifact, StaticAnalysis
from app.sandbox_bridge import enqueue_analysis, read_result
from app.worker import app

logger = logging.getLogger("tasks")


@app.task(name="analyze_artifact")
def analyze_artifact(artifact_id: str) -> None:
    new_trace_id()
    settings = get_settings()
    session = SessionLocal()
    try:
        artifact = session.get(ApplicationArtifact, artifact_id)
        if artifact is None or artifact.upload_status != "uploaded":
            logger.info("analyze_artifact: artifact missing or not uploaded")
            return
        if not artifact.internal_storage_key:
            logger.info("analyze_artifact: artifact has no stored file")
            return

        analysis = (
            session.query(StaticAnalysis).filter_by(artifact_id=artifact_id).one_or_none()
        )
        if analysis is None:
            analysis = StaticAnalysis(artifact_id=artifact_id, status="analyzing")
            session.add(analysis)
        else:
            analysis.status = "analyzing"
            analysis.error = None
            # Clear prior discoveries so a re-analysis is not additive (idempotent result).
            analysis.discoveries.clear()
        session.commit()

        # Hand off to the sandbox (idempotent).
        enqueue_analysis(artifact_id, artifact.internal_storage_key, artifact.sha256 or "")
        logger.info("analyze_artifact: handed off to sandbox", extra={"extra": {"artifact_id": artifact_id}})

        # Wait for the sandbox result (bounded).
        deadline = time.monotonic() + settings.analysis_timeout_seconds
        result = None
        while time.monotonic() < deadline:
            result = read_result(artifact_id)
            if result is not None:
                break
            time.sleep(settings.analysis_poll_seconds)

        if result is None:
            analysis.status = "failed"
            analysis.error = "sandbox analysis timed out"
            session.commit()
            logger.info("analyze_artifact: timed out")
            return

        if result.status == "error" or result.payload is None:
            analysis.status = "failed"
            analysis.error = result.error or "sandbox reported an error"
            session.commit()
            logger.info("analyze_artifact: sandbox error", extra={"extra": {"error": analysis.error}})
            return

        # Validate untrusted payload and persist discoveries with provenance.
        try:
            ingest(analysis, result.payload)
            # Backfill package/version onto the artifact for convenience.
            mf = result.payload.get("manifest") or {}
            if isinstance(mf, dict):
                artifact.package_identifier = mf.get("package") or artifact.package_identifier
                artifact.version = mf.get("version_name") or artifact.version
            session.commit()
            logger.info("analyze_artifact: analyzed", extra={"extra": {"artifact_id": artifact_id}})
        except Exception as exc:  # noqa: BLE001 - malformed sandbox output is a failure, not a crash
            session.rollback()
            analysis = session.query(StaticAnalysis).filter_by(artifact_id=artifact_id).one()
            analysis.status = "failed"
            analysis.error = f"invalid sandbox output: {type(exc).__name__}: {exc}"
            session.commit()
            logger.info("analyze_artifact: invalid sandbox output")
    finally:
        session.close()
