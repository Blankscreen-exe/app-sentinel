#!/usr/bin/env bash
# Switch the lab between 'broken' and 'correct' modes (and reset data).
# Applies the base schema + the chosen RLS overlay, then tells PostgREST to reload.
#
# Usage:  ./mode.sh broken   |   ./mode.sh correct
set -euo pipefail

MODE="${1:-}"
if [ "$MODE" != "broken" ] && [ "$MODE" != "correct" ]; then
  echo "usage: $0 broken|correct" >&2
  exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
DC=(docker compose -f "$HERE/docker-compose.lab.yml")

echo "{\"logger\":\"lab\",\"message\":\"applying base schema\"}"
"${DC[@]}" exec -T lab-db psql -U postgres -d postgres -v ON_ERROR_STOP=1 < "$HERE/sql/00_schema.sql"

echo "{\"logger\":\"lab\",\"message\":\"applying $MODE overlay\"}"
"${DC[@]}" exec -T lab-db psql -U postgres -d postgres -v ON_ERROR_STOP=1 < "$HERE/sql/10_${MODE}.sql"

# Ask PostgREST to reload its schema cache.
"${DC[@]}" exec -T lab-db psql -U postgres -d postgres -c "NOTIFY pgrst, 'reload schema';" >/dev/null

echo "{\"logger\":\"lab\",\"message\":\"lab is now in '$MODE' mode\"}"
