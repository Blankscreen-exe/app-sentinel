#!/usr/bin/env bash
# Connect the platform worker to the lab network so the agent can reach the lab target.
# Run after both the main stack and the lab are up. Idempotent.
#
# The agent reaches the lab at http://lab-rest:3000; the scope gate still blocks it unless
# the assessment explicitly authorizes the lab target (allow_lab_targets + authorized_hosts).
set -euo pipefail

WORKER="$(docker compose ps -q worker 2>/dev/null || true)"
[ -z "$WORKER" ] && WORKER="app_sentinel-worker-1"

if docker network connect app_sentinel_lab-net "$WORKER" 2>/dev/null; then
  echo "connected $WORKER to app_sentinel_lab-net"
else
  echo "already connected (or network/worker not found)"
fi
