# LLM gateway (placeholder for the foundation).
# Real Claude CLI wrapping (tools disabled, schema-validated JSON out) arrives in
# step 3. This process only answers a health ping so compose wiring is verifiable.
# It is the only service that will hold the Claude credential (ADR-003); none yet.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /srv
COPY main.py .

RUN useradd --create-home --uid 1000 gatewayuser
USER gatewayuser

EXPOSE 9000
CMD ["python", "main.py"]
