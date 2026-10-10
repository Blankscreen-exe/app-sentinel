# Sandbox worker (placeholder for the foundation).
# Real androguard + JADX analysis arrives in step 2. This process only proves the
# container is on the isolated network and alive. No internet, no credentials.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /srv
COPY worker.py .

RUN useradd --create-home --uid 1000 sandboxuser
USER sandboxuser

CMD ["python", "worker.py"]
