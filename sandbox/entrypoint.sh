#!/usr/bin/env bash
# Initialize sandbox-db (Procrastinate queue schema + the result table), then run
# the worker. Idempotent and fail-hard.
set -euo pipefail

# Capture the exit code without `set -e` aborting on the intentional "schema absent"
# signal (exit 7).
rc=0
python - <<'PY' || rc=$?
import os, psycopg, sys
dsn = os.environ["SANDBOX_DATABASE_URL"]
with psycopg.connect(dsn) as conn:
    present = conn.execute(
        "SELECT to_regclass('public.procrastinate_jobs')"
    ).fetchone()[0]
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sandbox_result (
            artifact_id text PRIMARY KEY,
            sha256 text NOT NULL,
            status text NOT NULL,
            payload jsonb,
            error text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()
sys.exit(0 if present else 7)
PY
if [ "$rc" = "7" ]; then
  echo '{"logger":"sandbox","message":"applying procrastinate schema to sandbox-db"}'
  procrastinate --app=sandbox_app.app schema --apply
fi

echo '{"logger":"sandbox","message":"starting sandbox worker"}'
exec procrastinate --app=sandbox_app.app worker
