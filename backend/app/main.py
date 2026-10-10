"""FastAPI application: dashboard page, real health check, trivial job enqueue.

Local-only posture (ADR-007): bound to localhost by compose; the API still
enforces a Host-header allowlist and a custom-header requirement on state-changing
requests so a browser page on the same machine cannot drive it (anti-CSRF / anti
DNS-rebinding).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.logging_setup import configure_logging, new_trace_id
from app.models import Project
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
