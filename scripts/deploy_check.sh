#!/usr/bin/env bash
# Assert that a stack brought up by `make prod-up` is actually serving, not just
# running. Containers report healthy long before the app is usable -- a database
# accepts connections with no tables, and nginx serves an index that fails on
# its first API call -- so check the things a demo would break on.
set -uo pipefail

COMPOSE="docker compose -f infra/docker-compose.prod.yml"
WEB_PORT="${WEB_HOST_PORT:-80}"
API_PORT="${API_HOST_PORT:-8000}"
FAIL=0

check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "ok      $label"
  else
    echo "FAILED  $label"
    FAIL=1
  fi
}

echo "=== containers ==="
$COMPOSE ps

for svc in postgres redis neo4j backend frontend; do
  state=$($COMPOSE ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s{print $2}')
  if [ "$state" = "running" ]; then
    echo "ok      $svc running"
  else
    echo "FAILED  $svc is '${state:-absent}'"
    FAIL=1
  fi
done

echo
echo "=== backend ==="
health=$(curl -fsS "http://localhost:${API_PORT}/health" 2>/dev/null)
if [ -z "$health" ]; then
  echo "FAILED  /health unreachable on ${API_PORT}"
  FAIL=1
else
  down=$(printf '%s' "$health" | grep -o '"down"' | wc -l | tr -d ' ')
  if [ "$down" = "0" ]; then
    echo "ok      /health reports no down dependency"
  else
    echo "FAILED  /health reports $down dependency(ies) down"
    printf '        %s\n' "$health"
    FAIL=1
  fi
fi

# A migrated database is the difference between a stack that boots and one that
# answers. Anything other than an empty list means alembic ran.
check "schema migrated" bash -c \
  "$COMPOSE exec -T postgres psql -U \${POSTGRES_USER:-copilot} -d \${POSTGRES_DB:-copilot} -tAc \
   \"select 1 from information_schema.tables where table_name='visits'\" | grep -q 1"

check "openapi served" bash -c \
  "curl -fsS http://localhost:${API_PORT}/openapi.json | grep -q '\"/api/v1/visits/{visit_id}\"'"

echo
echo "=== frontend ==="
check "index served on ${WEB_PORT}" curl -fsS "http://localhost:${WEB_PORT}/"
# The proxy is the whole reason the bundle ships with a relative API base; if it
# is misconfigured the app loads and then fails on every request. An unauthorised
# call is the cheapest probe that proves the request reached the API: the error
# envelope can only have come from the backend, whereas the SPA fallback would
# answer any path at all with index.html and a 200.
check "api proxied through nginx" bash -c \
  "curl -sS http://localhost:${WEB_PORT}/api/v1/auth/me | grep -q '\"error\"'"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "DEPLOY OK"
else
  echo "DEPLOY CHECK FAILED"
fi
exit $FAIL
