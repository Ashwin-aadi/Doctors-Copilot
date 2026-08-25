#!/usr/bin/env bash
set -euo pipefail
BASE="${VITE_API_BASE:-http://localhost:8000}"

echo "=== smoke: health ==="
curl -sf "$BASE/health" | jq -e '[.[]|select(.=="down")]|length==0' >/dev/null

echo "=== smoke: openapi path count ==="
python scripts/gen_openapi.py
python -c "
import json
s = json.load(open('openapi.json'))
n = len(s['paths'])
assert n >= 40, n
print('paths', n)
"

echo "=== smoke: triage flow ==="
SID=$(curl -sf -XPOST "$BASE/api/v1/triage/session" -H 'Content-Type: application/json' -d '{}' | jq -r .session_id)
curl -sf -XPOST "$BASE/api/v1/triage/$SID/message" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"content\":\"crushing chest pain radiating to left arm, sweating, 40 minutes\"}" >/dev/null
curl -sf "$BASE/api/v1/triage/$SID/result" \
  | jq -e '.severity_esi<=2 and (.citations|length)>=2 and (.suggested_labs|length)>=2' >/dev/null

echo "SMOKE OK"
