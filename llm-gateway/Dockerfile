# LLM gateway (ADR-002/003/015): wraps the Claude CLI as prompt-in / JSON-out.
# The only credential-holding component. Credentials are injected at RUNTIME
# (mounted ~/.claude or an API key / secret), never baked into this image.
FROM node:20-bookworm-slim

# Python (stdlib only) runs the small HTTP server; Node runs the Claude CLI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI. Pinned to match the host version (ADR-003); update deliberately.
RUN npm install -g @anthropic-ai/claude-code@2.1.286 || npm install -g @anthropic-ai/claude-code@latest

ENV PYTHONUNBUFFERED=1 \
    CLAUDE_CONFIG_DIR=/home/node/.claude
WORKDIR /srv
COPY server.py entrypoint.sh ./

# The node:20 image already ships a non-root `node` user at uid 1000, which matches the
# host operator so a mounted ~/.claude seed is readable. Reuse it rather than creating one.
USER node

EXPOSE 9000
CMD ["bash", "entrypoint.sh"]
