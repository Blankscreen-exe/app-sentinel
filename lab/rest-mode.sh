#!/usr/bin/env bash
# Switch the mock REST API lab between 'broken' (missing auth) and 'correct' (401).
# Usage: ./rest-mode.sh broken|correct
set -euo pipefail
MODE="${1:-}"
[ "$MODE" = "broken" ] || [ "$MODE" = "correct" ] || { echo "usage: $0 broken|correct" >&2; exit 2; }
curl -s -X POST "http://127.0.0.1:8080/__mode/$MODE" >/dev/null
echo "{\"logger\":\"restapi-lab\",\"message\":\"REST lab now in '$MODE' mode\"}"
