# Sandbox worker: runs androguard static analysis on untrusted APKs.
# Isolated network (no internet egress), no credentials (ADR-005). Reads APKs from
# shared storage mounted read-only; talks only to sandbox-db.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    PYTHONPATH=/srv \
    JADX_VERSION=1.5.0

WORKDIR /srv

# JADX (DEX -> Java decompiler) needs a JRE. Pinned release, installed to /opt/jadx.
# The download happens at BUILD time (has internet); at runtime the sandbox has none.
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless unzip curl ca-certificates \
    && curl -fsSL -o /tmp/jadx.zip \
        "https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip" \
    && mkdir -p /opt/jadx && unzip -q /tmp/jadx.zip -d /opt/jadx \
    && ln -s /opt/jadx/bin/jadx /usr/local/bin/jadx \
    && rm -rf /tmp/jadx.zip /var/lib/apt/lists/*

# Pinned analysis + queue dependencies.
RUN uv pip install --system \
    "androguard==4.1.4" \
    "procrastinate==3.10.0" \
    "psycopg[binary]==3.2.3"

COPY analyzer.py scanner.py sandbox_app.py entrypoint.sh ./

RUN useradd --create-home --uid 1000 sandboxuser
USER sandboxuser

CMD ["bash", "entrypoint.sh"]
