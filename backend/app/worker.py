"""Procrastinate app and a trivial job.

The trivial job exists to prove the queue works end to end in the foundation
(acceptance criterion 4). Real assessment tasks replace/extend this later.
"""

from __future__ import annotations

import logging

from procrastinate import App, PsycopgConnector

from app.config import get_settings
from app.logging_setup import configure_logging, new_trace_id

_settings = get_settings()
configure_logging(_settings.log_level)
logger = logging.getLogger("worker")


def _connector() -> PsycopgConnector:
    # Procrastinate uses psycopg (v3). It wants a plain libpq DSN, not the
    # SQLAlchemy "+psycopg" form.
    return PsycopgConnector(conninfo=_settings.main_database_url)


app = App(connector=_connector())


@app.task(name="ping")
def ping(message: str = "pong") -> str:
    """Trivial task: logs and returns, proving enqueue -> execute works."""
    tid = new_trace_id()
    logger.info("ping task executed", extra={"extra": {"message": message, "trace_id": tid}})
    return message
