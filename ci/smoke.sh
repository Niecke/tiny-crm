#!/usr/bin/env bash
# Integration test for the built images: starts backend + frontend + Postgres +
# MinIO from compose.ci.yml and drives one real workflow through the API.
#
#   IMAGE_TAG=ci-abc1234 ci/smoke.sh
#
# Fails on the first problem. Container logs are printed by the caller (the
# workflow dumps them on failure), so this only reports what it checked.
set -euo pipefail

cd "$(dirname "$0")/.."

: "${IMAGE_TAG:?set IMAGE_TAG to the tag that was just pushed}"
export REGISTRY="${REGISTRY:-europe-west1-docker.pkg.dev/niecke-it/tiny-crm}"
# Throwaway, but not the built-in defaults: the backend runs with
# ENVIRONMENT=production, which refuses to start on placeholder credentials.
export JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
export S3_ACCESS_KEY="${S3_ACCESS_KEY:-ci-access-key}"
export S3_SECRET_KEY="${S3_SECRET_KEY:-ci-secret-key-$(openssl rand -hex 8)}"

# Overridable so the same script rehearses locally against podman and
# locally-built images: COMPOSE_CMD="podman-compose" PULL_POLICY=never ...
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
PULL_POLICY="${PULL_POLICY:-always}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_PORT="${FRONTEND_PORT:-8080}"

COMPOSE="$COMPOSE_CMD -p tinycrm-ci -f compose.ci.yml"
API="http://localhost:$BACKEND_PORT"
WEB="http://localhost:$FRONTEND_PORT"
EMAIL="ci@example.com"
PASSWORD="ci-password-$(openssl rand -hex 6)"

step() { printf '\n=== %s\n' "$1"; }
fail() { printf 'FAILED: %s\n' "$1" >&2; exit 1; }

json() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

wait_for() {  # wait_for <name> <url> <seconds>
  local name=$1 url=$2 deadline=$((SECONDS + $3))
  until curl -fsS "$url" > /dev/null 2>&1; do
    [ $SECONDS -lt $deadline ] || fail "$name did not come up within $3s ($url)"
    sleep 2
  done
}

step "starting the stack ($IMAGE_TAG)"
$COMPOSE up -d --pull "$PULL_POLICY"

step "backend is healthy and reached its database"
wait_for backend "$API/health" 120
health=$(curl -fsS "$API/health")
[ "$(echo "$health" | json "['status']")" = "ok" ] || fail "backend unhealthy: $health"
[ "$(echo "$health" | json "['db']")" = "ok" ] || fail "backend cannot reach the database: $health"

step "both images report the commit they were built from"
backend_version=$(curl -fsS "$API/version" | json "['version']")
frontend_version=$(curl -fsS "$WEB/version.json" | json "['version']")
[ -n "$backend_version" ] && [ "$backend_version" != "unknown" ] \
  || fail "backend reports version '$backend_version'"
[ "$backend_version" = "$frontend_version" ] \
  || fail "version mismatch: backend $backend_version, frontend $frontend_version"
if [ -n "${EXPECTED_COMMIT:-}" ]; then
  [ "$backend_version" = "$EXPECTED_COMMIT" ] \
    || fail "images report $backend_version, expected $EXPECTED_COMMIT"
fi

step "frontend serves the Flutter bundle"
curl -fsS "$WEB/" | grep -q 'flutter_bootstrap.js' || fail "index.html is not the Flutter app"
# Unknown paths fall back to index.html so deep links work after a reload.
curl -fsS "$WEB/interactions" | grep -q 'flutter_bootstrap.js' || fail "SPA fallback is broken"

step "migrations ran and the admin CLI works"
$COMPOSE exec -T -e PYTHONPATH=/app backend python scripts/create_admin.py "$EMAIL" "$PASSWORD" \
  | grep -q "created" || fail "could not create the admin user"

step "login returns a token"
token=$(curl -fsS -X POST "$API/auth/jwt/login" \
  -d "username=$EMAIL&password=$PASSWORD" | json "['access_token']")
[ -n "$token" ] || fail "login did not return a token"
auth=(-H "Authorization: Bearer $token")

step "unauthenticated requests are rejected"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/contacts/")" = "401" ] \
  || fail "GET /contacts/ without a token should be 401"

step "a contact round-trips through Postgres"
contact_id=$(curl -fsS -X POST "$API/contacts/" "${auth[@]}" \
  -H 'Content-Type: application/json' \
  -d '{"name":"CI Smoke","tags":["ci"]}' | json "['id']")
[ -n "$contact_id" ] || fail "contact was not created"
total=$(curl -fsS "$API/contacts/?search=CI%20Smoke" "${auth[@]}" | json "['total']")
[ "$total" = "1" ] || fail "expected 1 contact from search, got $total"

step "a document round-trips through MinIO"
printf 'tinyCRM integration test\n' > /tmp/ci-smoke.txt
document_id=$(curl -fsS -X POST "$API/documents/" "${auth[@]}" \
  -F "title=CI Smoke" -F "tags=[]" -F "file=@/tmp/ci-smoke.txt" | json "['id']")
[ -n "$document_id" ] || fail "document was not created"
curl -fsS "$API/documents/$document_id/content" "${auth[@]}" -o /tmp/ci-smoke-download.txt
diff -q /tmp/ci-smoke.txt /tmp/ci-smoke-download.txt > /dev/null \
  || fail "downloaded document differs from what was uploaded"

step "cleanup"
curl -fsS -X DELETE "$API/documents/$document_id" "${auth[@]}"
curl -fsS -X DELETE "$API/contacts/$contact_id" "${auth[@]}"

printf '\nAll integration checks passed for %s (commit %s)\n' "$IMAGE_TAG" "$backend_version"
