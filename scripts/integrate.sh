#!/usr/bin/env bash
set -euo pipefail
CP="${1:?usage: integrate.sh <cp-number>}"
git checkout main && git pull --ff-only origin main
for m in virat pratyaksh niyati divyanshi abhishek; do
  B="feat/$m/cp$CP"
  git fetch origin "$B" 2>/dev/null || { echo "SKIP $B (absent)"; continue; }
  echo "=== merging $B ==="
  git merge --no-ff "origin/$B" -m "merge: integrate $m cp$CP" || {
    echo "CONFLICT in $B"; git diff --name-only --diff-filter=U; exit 1; }
done
