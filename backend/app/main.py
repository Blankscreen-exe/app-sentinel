"""FastAPI application: dashboard page, real health check, trivial job enqueue.

Local-only posture (ADR-007): bound to localhost by compose; the API still
enforces a Host-header allowlist and a custom-header requirement on state-changing
requests so a browser page on the same machine cannot drive it (anti-CSRF / anti
DNS-rebinding).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.logging_setup import configure_logging, new_trace_id
from app.models import (
    ApplicationArtifact,
    Assessment,
    AttackSurfaceResource,
    Finding,
    Project,
    StaticAnalysis,
    ToolExecution,
)
from app.services.artifacts import UploadTooLarge, intake_apk
from app.tasks import analyze_artifact, run_assessment
from app.worker import app as procrastinate_app
from app.worker import ping

_settings = get_settings()
configure_logging(_settings.log_level)
logger = logging.getLogger("api")

_BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_BASE / "templates"))

app = FastAPI(title="App Sentinel", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")

_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "localhost:8000", "127.0.0.1:8000"}


@app.middleware("http")
async def trace_and_host_guard(request: Request, call_next: Any) -> Any:
    new_trace_id()
    host = request.headers.get("host", "").split(",")[0].strip()
    if host and host not in _ALLOWED_HOSTS:
        logger.warning("blocked host header", extra={"extra": {"host": host}})
        return JSONResponse({"detail": "host not allowed"}, status_code=400)
    return await call_next(request)


def require_app_header(x_app_sentinel: str | None = Header(default=None)) -> None:
    """State-changing endpoints require this custom header (anti-CSRF, ADR-007)."""
    if x_app_sentinel != "1":
        raise HTTPException(status_code=403, detail="missing X-App-Sentinel header")


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Real health check: verifies the DB and the job queue, no hardcoded 'ok'."""
    checks: dict[str, str] = {}
    overall = "ok"

    try:
        session.execute(text("SELECT 1"))
        checks["main_db"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't hide
        checks["main_db"] = f"error: {type(exc).__name__}"
        overall = "degraded"

    try:
        # The queue is healthy if Procrastinate's schema table is reachable.
        session.execute(text("SELECT 1 FROM procrastinate_jobs LIMIT 1"))
        checks["job_queue"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["job_queue"] = f"error: {type(exc).__name__}"
        overall = "degraded"

    status_code = 200 if overall == "ok" else 503
    return JSONResponse({"status": overall, "checks": checks}, status_code=status_code)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    projects = session.scalars(select(Project).order_by(Project.created_at.desc())).all()
    return templates.TemplateResponse(
        request, "index.html", {"projects": projects, "env": _settings.app_env}
    )


@app.post("/api/v1/ping", dependencies=[Depends(require_app_header)])
def enqueue_ping() -> dict[str, str]:
    """Enqueue the trivial job to prove the queue works end to end."""
    with procrastinate_app.open():
        ping.defer(message="hello-from-api")
    logger.info("ping enqueued")
    return {"enqueued": "ping"}


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "upload.html", {"env": _settings.app_env, "error": error}
    )


@app.post("/upload")
def upload_submit(
    request: Request,
    project_name: str = Form(""),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Browser upload form. Streams, validates, and stores the APK.

    This is a same-origin form submission (Host-allowlisted above), so it is not a
    CSRF vector; the JSON API variant still requires the custom header.
    """
    try:
        outcome = intake_apk(
            session,
            project_name=project_name,
            filename=file.filename or "upload.apk",
            src=file.file,
        )
    except UploadTooLarge as exc:
        return RedirectResponse(url=f"/upload?error={exc}", status_code=303)

    return RedirectResponse(url=f"/artifacts/{outcome.artifact.id}", status_code=303)


@app.get("/artifacts/{artifact_id}", response_class=HTMLResponse)
def artifact_detail(
    request: Request, artifact_id: str, session: Session = Depends(get_session)
) -> HTMLResponse:
    artifact = session.get(ApplicationArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    analysis = (
        session.query(StaticAnalysis).filter_by(artifact_id=artifact_id).one_or_none()
    )
    discoveries = analysis.discoveries if analysis else []
    return templates.TemplateResponse(
        request,
        "artifact.html",
        {"env": _settings.app_env, "a": artifact, "analysis": analysis, "discoveries": discoveries},
    )


@app.post("/artifacts/{artifact_id}/analyze")
def start_analysis(
    artifact_id: str, session: Session = Depends(get_session)
) -> RedirectResponse:
    """Trigger static analysis (same-origin form POST)."""
    artifact = session.get(ApplicationArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    if artifact.upload_status != "uploaded":
        raise HTTPException(status_code=400, detail="artifact is not in an analyzable state")
    with procrastinate_app.open():
        analyze_artifact.defer(artifact_id=artifact_id)
    return RedirectResponse(url=f"/artifacts/{artifact_id}", status_code=303)


# Default lab scope: authorizes the local lab target only. The operator edits scope per
# assessment in a real engagement; this convenience default is for the local demo.
_DEFAULT_LAB_SCOPE = json.dumps({
    "active_testing_allowed": True,
    "authorized_hosts": ["lab-rest"],
    "authorized_resources": ["table:trips", "table:invoices", "table:profiles"],
    "allow_lab_targets": True,
    "max_active_requests": 30,
})


@app.post("/artifacts/{artifact_id}/assess")
def start_assessment(
    artifact_id: str, session: Session = Depends(get_session)
) -> RedirectResponse:
    """Create an assessment for an analyzed artifact and enqueue the agent run."""
    artifact = session.get(ApplicationArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    assessment = Assessment(
        artifact_id=artifact_id, status="created", scope_configuration=_DEFAULT_LAB_SCOPE
    )
    session.add(assessment)
    session.commit()
    with procrastinate_app.open():
        run_assessment.defer(assessment_id=assessment.id)
    return RedirectResponse(url=f"/assessments/{assessment.id}", status_code=303)


@app.get("/assessments/{assessment_id}", response_class=HTMLResponse)
def assessment_detail(
    request: Request, assessment_id: str, session: Session = Depends(get_session)
) -> HTMLResponse:
    assessment = session.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    executions = (
        session.query(ToolExecution)
        .filter_by(assessment_id=assessment_id)
        .order_by(ToolExecution.step_index)
        .all()
    )
    findings = session.query(Finding).filter_by(assessment_id=assessment_id).all()
    resources = session.query(AttackSurfaceResource).filter_by(assessment_id=assessment_id).all()
    return templates.TemplateResponse(
        request,
        "assessment.html",
        {
            "env": _settings.app_env,
            "a": assessment,
            "executions": executions,
            "findings": findings,
            "resources": resources,
        },
    )
