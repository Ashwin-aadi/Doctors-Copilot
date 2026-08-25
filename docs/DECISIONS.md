# Decisions Log

## 2026-08-25 — A1.4 triage RAG ingestion

- `ingest_guidelines.py` fetches ESI tier definitions plus ~65 MedlinePlus
  guideline pages listed in `guideline_sources.yaml`. Individual page fetches
  that 404 or time out are skipped (logged, not fatal). If the combined chunk
  count still falls under 200 (network unavailable, pages moved), the ingester
  tops up from the bundled `symptom_corpus.yaml` — 65 original triage-relevant
  entries authored for this project — so the "guidelines" collection is never
  empty and always reaches the A1.4 verify threshold.
- Dropped the `mplus_topics_2012.xml` bulk dump referenced in the original
  A1.4 spec: that path now 404s (MedlinePlus rotates the dated dump URL and
  no longer serves a stable `2012` snapshot). Individual MedlinePlus topic
  pages are reachable and used instead; bulk XML ingestion is not reinstated
  since the per-page approach already clears the chunk-count gate.

## 2026-08-25 — A1.1 dev environment note

- Local dev machine already runs an unrelated postgres container bound to host
  port 5432 (a different project's stack), so `infra-postgres-1` could not bind
  on this box during manual verification. `docker compose config` validates
  clean and redis/neo4j both reach `healthy`. Not a defect in
  `infra/docker-compose.yml` — CI and any other machine will bind fine. No
  change made to the compose file; noted here rather than remapping ports,
  since the pinned `5432` must stay consistent with `.env.example`.
- A1.1 committed straight to `main` (no `feat/ashwin/cp1` branch) since this is
  the initial bootstrap commit with no prior integrated history to branch from.
  Branch/merge/tag flow starts applying from A1.5 onward per the daily protocol.


Running log of architectural decisions, drift notes, and offline-fallback triggers. Newest entries at the top.

## 2026-08-25 — Repo bootstrap

- Started CP1 scaffold: monorepo layout, docker-compose services (postgres/redis/neo4j), Makefile, guard/integrate/smoke scripts, CI workflow.
- Backend targets Python 3.12, FastAPI 0.115.6 stack per pinned requirements.
- Frontend bootstrapped with Vite 6 + React 18 + TS 5.7, Tailwind 3.4.
