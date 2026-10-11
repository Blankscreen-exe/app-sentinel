# Backend image: serves the API and runs the worker (same code, different command).
FROM python:3.12-slim

# uv for fast, reproducible installs (ADR-004).
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    PYTHONPATH=/srv

# PYTHONPATH=/srv so the `procrastinate` console-script can import the `app`
# package (a console-script, unlike `python`, does not add the cwd to sys.path).

WORKDIR /srv

# System libraries for WeasyPrint (HTML->PDF report export).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        libjpeg62-turbo libopenjp2-7 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for layer caching.
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY . .

# Non-root (ADR-004c). UID/GID are overridden at runtime for bind-mount access.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
