#!/usr/bin/env bash
set -euo pipefail
PAT='claude|anthropic|co-authored-by|generated with|🤖|ai-generated|llm-generated'
FAIL=0
if git log origin/main..HEAD --format='%an%n%ae%n%B' 2>/dev/null | grep -Eiq "$PAT"; then
  echo "BLOCKED: assistant footprint in commit metadata"; FAIL=1; fi
if git diff origin/main..HEAD --name-only 2>/dev/null | grep -Eq '^(\.claude/|CLAUDE.*\.md|\.mcp\.json|\.env$)'; then
  echo "BLOCKED: assistant/secret file staged"; FAIL=1; fi
if git grep -Eil "$PAT" -- ':!docs/MODELS.md' ':!*.lock' ':!package-lock.json' ':!scripts/guard.sh' 2>/dev/null | grep -q .; then
  echo "BLOCKED: footprint in tracked source"
  git grep -Eil "$PAT" -- ':!docs/MODELS.md' ':!*.lock' ':!package-lock.json' ':!scripts/guard.sh'; FAIL=1; fi
[ "$FAIL" -eq 0 ] && echo "GUARD OK"
exit $FAIL
