# Sandbox worker: runs androguard static analysis on untrusted APKs.
# Isolated network (no internet egress), no credentials (ADR-005). Reads APKs from
# shared storage mounted read-only; talks only to sandbox-db.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    PYTHONPATH=/srv

WORKDIR /srv

# Pinned analysis + queue dependencies.
RUN uv pip install --system \
    "androguard==4.1.4" \
    "procrastinate==3.10.0" \
    "psycopg[binary]==3.2.3"

COPY analyzer.py scanner.py sandbox_app.py entrypoint.sh ./

RUN useradd --create-home --uid 1000 sandboxuser
USER sandboxuser

CMD ["bash", "entrypoint.sh"]
