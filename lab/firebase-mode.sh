#!/usr/bin/env bash
# Switch the mock Firebase RTDB lab between 'broken' (open rules) and 'correct' (locked).
# Usage: ./firebase-mode.sh broken|correct
set -euo pipefail
MODE="${1:-}"
[ "$MODE" = "broken" ] || [ "$MODE" = "correct" ] || { echo "usage: $0 broken|correct" >&2; exit 2; }
curl -s -X POST "http://127.0.0.1:9000/__mode/$MODE" >/dev/null
echo "{\"logger\":\"firebase-lab\",\"message\":\"firebase lab now in '$MODE' mode\"}"
