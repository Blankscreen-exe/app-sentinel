#!/usr/bin/env bash
# One-shot init: apply our schema (Alembic) and Procrastinate's queue schema.
# Idempotent and fail-hard: errors must surface, never be swallowed.
set -euo pipefail

echo '{"level":"INFO","logger":"init","message":"applying alembic migrations"}'
alembic upgrade head

# Procrastinate's `schema --apply` is not idempotent (it would error on existing
# objects), so apply it only when the queue schema is absent. We check explicitly
# rather than ignoring errors.
if python -c "
import sys
from sqlalchemy import create_engine, text
from app.db import _engine_url
from app.config import get_settings
e = create_engine(_engine_url(get_settings().main_database_url))
with e.connect() as c:
    present = c.execute(text(\"SELECT to_regclass('public.procrastinate_jobs')\")).scalar()
sys.exit(0 if present else 1)
"; then
  echo '{"level":"INFO","logger":"init","message":"procrastinate schema already present"}'
else
  echo '{"level":"INFO","logger":"init","message":"applying procrastinate schema"}'
  procrastinate --app=app.worker.app schema --apply
fi

echo '{"level":"INFO","logger":"init","message":"init complete"}'
