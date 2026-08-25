# Contributing

## Branches

- One branch per person per checkpoint: `feat/<member>/cp<N>` (e.g. `feat/virat/cp2`).
- Never commit directly to `main` outside the daily integration step.

## Daily flow

1. Team lead integrates the previous checkpoint into `main` and tags `cp<N-1>-integrated`.
2. Each member branches from `main`, does their checkpoint work, opens a PR (or pushes for integration).
3. Merge order into `main` each day: `ashwin → virat → pratyaksh → niyati → divyanshi → abhishek`.
4. Each checkpoint ends with `make test && make smoke && ./scripts/guard.sh` passing before merge.

## Commits

- Conventional Commits: `feat(scope): subject`, `fix(scope): subject`, `chore(scope): subject`, etc.
- Scopes: `infra, db, schemas, api, llm, rag, kg, visit, ci, docs, test`.
- Imperative mood, subject line ≤72 chars, body explains what changed and why.
- No co-author trailers. Write commits in your own voice as the sole author.

## Code style

- Backend: `ruff check .` must pass; format with `ruff format` conventions.
- Frontend: `npm run lint` and `tsc --noEmit` must pass.
- Keep changes scoped to your owned paths (see the ownership map in the root spec). If you need a
  change in a teammate's file, log it in `docs/DECISIONS.md` under a `DRIFT:` entry instead of editing it directly.

## Tests

- `make test` runs backend pytest + frontend vitest.
- `make smoke` runs the end-to-end smoke harness against a running stack.
- New endpoints need at least one integration test in `backend/tests/integration/`.
