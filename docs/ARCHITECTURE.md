# Architecture

## Overview

Doctor's Copilot is a single FastAPI backend + Vite/React frontend, backed by
Postgres (relational data), Neo4j (patient knowledge graph), Chroma
(vector search), and Redis (cache, queues, pub/sub). All clinical text
generation goes through one LLM gateway (`app/llm/gateway.py`) that chains
Groq → local Ollama → an extractive fallback, so the product degrades
gracefully rather than failing when a credential or model is unavailable.

```
frontend (Vite/React) ── REST + WS ──> backend (FastAPI)
                                          ├── db/          Postgres via SQLAlchemy async ORM
                                          ├── llm/         Groq -> Ollama -> extractive gateway
                                          ├── rag/         Chroma vector store + hybrid retriever
                                          ├── kg/          Neo4j patient knowledge graph
                                          ├── ml/          OCR, NER, interaction/safety checks
                                          └── services/    scheduling, queueing, rules, mapping
```

## RAG collections

| Collection | Embedding model | Populated by | Used by |
|---|---|---|---|
| `guidelines` | general (MiniLM, 384d) | `rag/ingest_guidelines.py` | pre-assessment triage (`rag/triage_rag.py`) |
| `clinical` | clinical (PubMedBERT, 768d) | `rag/ingest_clinical.py` (CP2) | doctor copilot brief (CP2) |
| `patient_{patient_id}` | general | `rag/ingest_patient.py` (CP3) | patient chatbot (CP3) |

Retrieval (`rag/retriever.hybrid`) always does BM25 + dense search, fuses with
Reciprocal Rank Fusion (k=60), then reranks the fused candidates with a
cross-encoder before returning the top-k. Every stored chunk carries
`source, title, url, section, doc_type, published` metadata so citations can
be traced back to their origin.

### Offline fallback

`ingest_guidelines.py` fetches ESI tier definitions plus public MedlinePlus
guideline pages. If a page 404s it's skipped; if the combined chunk count
still falls short of 200 (no network, pages moved), it tops up from the
bundled `app/rag/data/symptom_corpus.yaml` — 65 original triage-relevant
entries — so the collection is never empty. See `docs/DECISIONS.md` for the
specific trigger history.

## LLM gateway fallback chain

1. **Groq** (`llama-3.3-70b-versatile`) — used when `GROQ_API_KEY` is set.
2. **Ollama** (`llama3.1:8b`, local) — used when Groq is unavailable or unset.
3. **Extractive fallback** — a short deterministic summary of the prompt's
   own context, used when neither provider responds. `json_complete` falls
   back to a schema-default instance (safe defaults, `confidence: 0.0`)
   rather than raising, so every endpoint stays available.

Structured output (`json_complete`) retries with the pydantic validation
error fed back into the prompt (up to `retries` times) before giving up.

## Pre-assessment triage flow

`POST /api/v1/triage/session` → `POST /api/v1/triage/{id}/message` (up to 8
turns) → auto-finalizes into a `TriageResult` once a red flag fires (regex
pattern match, see `rag/data/esi_rules.yaml`, plus an LLM classifier) or the
question cap is hit. `GET /api/v1/triage/{id}/result` reads the persisted
result. Citations returned by the LLM are validated against the actual
retrieved chunks; anything that doesn't match a retrieved hit is dropped and
its `[n]` marker stripped from the rationale text.

## Windows dev note

`psycopg`'s async mode cannot run under Python's default `ProactorEventLoop`
on Windows. `app/db/session.py`, `app/main.py`, and `alembic/env.py` each set
`asyncio.WindowsSelectorEventLoopPolicy()` at import time (before any async
engine is created) as a guard — irrelevant on Linux/Docker, where the service
actually runs in CI and production.

## Seed data (fixed UUIDs)

`scripts/seed.py` is idempotent (safe to re-run) and creates:

| Entity | Count | ID pattern |
|---|---|---|
| Clinics | 3 | `00000000-0000-0000-0000-0000000000{01-03}` |
| Doctor users | 6 | `00000000-0000-0000-0000-0000000004{01-06}` |
| Doctors | 6 | `00000000-0000-0000-0000-0000000002{01-06}` |
| Patient users | 12 | `00000000-0000-0000-0000-0000000005{01-12}` |
| Patients | 12 | `00000000-0000-0000-0000-0000000001{01-12}` |
| Availability | 30 (5 weekdays x 6 doctors) | derived, 14-day rolling window |
| Demo visit | 1 | `00000000-0000-0000-0000-000000000301` |

Patient #1 (`...000101`) and the demo visit (`...000301`) are the IDs used in
later checkpoints' own verify scripts (knowledge graph sync, copilot brief),
so keep them stable if the seed script is ever restructured.

## Feature -> file map

| Feature | Backend | Frontend |
|---|---|---|
| Pre-assessment triage | `app/rag/triage_rag.py`, `app/api/v1/triage.py` | `src/features/*` (CP1.x, [B]) |
| Patient chatbot | `app/rag/patient_chat.py` (CP3) | — |
| Clinical copilot brief | `app/rag/clinical_rag.py` (CP2) | — |
| Knowledge graph | `app/kg/*` (CP2) | — |
| Doctor/appointment scheduling | `app/services/scheduling/*` ([N]) | — |
| OCR / lab parsing | `app/ml/*` ([V]) | — |
| Auth / captcha / approvals | `app/core/security.py`, `app/api/v1/auth.py` ([P]) | — |
