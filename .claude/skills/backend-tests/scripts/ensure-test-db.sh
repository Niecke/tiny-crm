#!/usr/bin/env bash
# Makes sure the in-memory test Postgres from compose.test.yml is up and accepting
# connections, starting it if needed. Touches no other container.
#
#   .claude/skills/backend-tests/scripts/ensure-test-db.sh
#
# Prints the TEST_DATABASE_URL to use on success; exits non-zero with the reason
# otherwise.
set -euo pipefail

cd "$(dirname "$0")/../../../.."

CONTAINER=tinycrm-test-db
PORT=55433
URL="postgresql+asyncpg://crm:crm@localhost:$PORT/postgres"

if command -v podman >/dev/null 2>&1; then
  ENGINE=podman
  COMPOSE="podman-compose -f compose.test.yml"
elif command -v docker >/dev/null 2>&1; then
  ENGINE=docker
  COMPOSE="docker compose -f compose.test.yml"
else
  echo "Neither podman nor docker is installed." >&2
  exit 1
fi

ready() {
  $ENGINE exec "$CONTAINER" pg_isready -q -U crm -d postgres 2>/dev/null
}

if ready; then
  echo "$URL"
  exit 0
fi

# Another process on the port would take our connections, and its credentials
# would not be ours. Report it instead of guessing.
running=$($ENGINE ps --filter "name=^$CONTAINER\$" --format '{{.Names}}')
if [ -z "$running" ] && ss -ltn 2>/dev/null | grep -qE "[:.]$PORT\b"; then
  echo "Port $PORT is taken by something other than $CONTAINER:" >&2
  ss -ltnp 2>/dev/null | grep -E "[:.]$PORT\b" >&2 || true
  exit 1
fi

echo "Starting $CONTAINER ..." >&2
$COMPOSE up -d >&2

for _ in $(seq 1 60); do
  if ready; then
    echo "$URL"
    exit 0
  fi
  sleep 0.5
done

echo "$CONTAINER did not become ready within 30s. Its log:" >&2
$ENGINE logs --tail 30 "$CONTAINER" >&2 || true
exit 1
