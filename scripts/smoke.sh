#!/usr/bin/env bash
set -euo pipefail
BASE="${VITE_API_BASE:-http://localhost:8000}"
export PYTHONPATH="$PWD/backend:${PYTHONPATH:-}"

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

echo "=== smoke: guidelines ingestion (skips if already populated) ==="
python -c "
import asyncio
from app.rag.store import VectorStore
from app.rag.ingest_guidelines import ingest

async def main():
    if VectorStore().count('guidelines') < 50:
        await ingest()

asyncio.run(main())
" 2>&1 | tail -5

echo "=== smoke: triage flow ==="
SID=$(curl -sf -XPOST "$BASE/api/v1/triage/session" -H 'Content-Type: application/json' -d '{}' | jq -r .session_id)
curl -sf -XPOST "$BASE/api/v1/triage/$SID/message" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"content\":\"crushing chest pain radiating to left arm, sweating, 40 minutes\"}" >/dev/null
RESULT=$(curl -sf "$BASE/api/v1/triage/$SID/result")
if [ -n "${GROQ_API_KEY:-}" ]; then
  echo "$RESULT" | jq -e '.severity_esi<=2 and .triage_colour=="red" and (.citations|length)>=2 and (.suggested_labs|length)>=2' >/dev/null
else
  echo "no GROQ_API_KEY set — checking degraded-but-valid shape instead of live citations"
  echo "$RESULT" | jq -e '.severity_esi<=2 and .triage_colour=="red" and (.red_flags|length)>=1' >/dev/null
fi

echo "=== smoke: India red-flag detection ==="
SID2=$(curl -sf -XPOST "$BASE/api/v1/triage/session" -H 'Content-Type: application/json' -d '{}' | jq -r .session_id)
curl -sf -XPOST "$BASE/api/v1/triage/$SID2/message" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID2\",\"content\":\"day 5 of fever, now bleeding gums and severe abdominal pain\"}" >/dev/null
curl -sf "$BASE/api/v1/triage/$SID2/result" | jq -e '.triage_colour=="red" and (.red_flags|length)>=1' >/dev/null

echo "SMOKE OK"
