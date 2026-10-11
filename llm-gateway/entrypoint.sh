#!/usr/bin/env bash
# Claude needs a WRITABLE config dir. We mount the operator's ~/.claude read-only as a
# seed and copy it to a writable location inside the container, so host credentials are
# never modified. If no seed is present, the gateway still starts (calls will fail until
# credentials are provided — the platform can run in LLM_MODE=stub/disabled).
set -e

if [ -d /seed/.claude ] && [ -n "$(ls -A /seed/.claude 2>/dev/null)" ]; then
  mkdir -p "$CLAUDE_CONFIG_DIR"
  cp -a /seed/.claude/. "$CLAUDE_CONFIG_DIR"/ 2>/dev/null || true
fi

exec python3 server.py
