# Architecture

## Built for Indian primary and secondary care

Every layer of this system assumes an Indian deployment, and that assumption is
load-bearing rather than cosmetic:

- **Clinical grounding is India-first.** Retrieval prefers Indian national guidance
  (MoHFW, NCVBDC, NTEP, NCDC, ICMR, NHM) and WHO material for the communicable and
  tropical burden that fills Indian OPDs, over international sources. Every chunk in
  the corpus carries a `region` of `IN` or `INTL` so a retriever can weight
  accordingly. International drug labels and RxNorm remain the pharmacology
  backbone — interaction chemistry is universal — but never the primary voice on
  first-line management or drug availability.
- **Triage speaks the local language of severity.** `severity_esi` stays the
  machine-readable 1–5 value, but every result also carries `triage_colour`, the
  MoHFW/AIIMS casualty code (ESI 1–2 red, 3 yellow, 4–5 green) that Indian triage
  counters and queue boards actually run on. `colour_for_esi()` in
  `app/schemas/triage.py` is the single source of that mapping.
- **Red flags match local presentations.** Alongside the universal emergencies,
  `app/rag/data/esi_rules.yaml` detects dengue warning signs, snakebite envenoming,
  organophosphate poisoning, heat stroke, febrile seizures, obstetric bleeding and
  severe paediatric dehydration.
- **Locale.** ₹ INR fees, `Asia/Kolkata`, `+91` phones, state + PIN addresses,
  optional ABHA ID on patients, NMC registration on doctors, and emergency copy that
  cites 112 / 108.
- **Regulation.** Consent and retention follow the DPDP Act 2023.

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
`source, title, url, section, doc_type, published, region` metadata so citations
can be traced back to their origin and Indian guidance can be preferred.

### Guideline sources, in priority order

`app/rag/data/guideline_sources.yaml` lists ~96 public pages in three bands:

1. **Indian government and programme material** (`region: IN`) — MoHFW national
   dengue management guidance, NCVBDC vector-borne programme pages, NTEP for
   tuberculosis, NCDC, ICMR, NHM, CDSCO, Jan Aushadhi, ABDM, and WHO India country
   pages.
2. **WHO fact sheets** for the Indian communicable and tropical burden — dengue,
   malaria, chikungunya, typhoid, TB, Japanese encephalitis, leishmaniasis,
   leptospirosis, cholera, hepatitis, snakebite envenoming, rabies, anaemia,
   rheumatic heart disease — plus the major non-communicable conditions.
3. **MedlinePlus** for plain-language coverage of the general symptom set.

### Offline fallback

If a page 404s it's skipped; if the combined chunk count still falls short of 200
(no network, pages moved), ingestion tops up from the bundled
`app/rag/data/symptom_corpus.yaml` — 84 original triage-relevant entries, of which
`sym-066` onward cover India-prevalent presentations (dengue warning signs, malaria,
enteric fever, chikungunya, TB, snakebite, pesticide poisoning, heat stroke,
gastroenteritis, nutritional anaemia, anaemia in pregnancy, rheumatic heart disease,
rabies exposure, scrub typhus, leptospirosis, uncontrolled diabetes, biomass COPD,
and fever beyond five days without a source). The collection is therefore never
empty and never loses its India specificity offline. See `docs/DECISIONS.md` for the
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

The result carries both `severity_esi` (1–5) and `triage_colour`, derived from it
by `colour_for_esi()`. A red-flag hit clamps severity to ESI ≤2, which means the
patient always comes out red, and the closing message directs them to the nearest
emergency department or to call 112 / 108.

The red-flag pattern list covers the universal emergencies (cardiac chest pain,
stroke signs, airway compromise, severe bleeding, suicidal ideation) plus the
presentations that matter in Indian practice: dengue warning signs (bleeding gums,
black stools, severe abdominal pain as the fever settles), snakebite with
neurotoxic features, pesticide and organophosphate ingestion, heat stroke, febrile
seizures and meningism, obstetric bleeding, animal bites needing rabies
prophylaxis, and severe paediatric dehydration.

## Windows dev note

`psycopg`'s async mode cannot run under Python's default `ProactorEventLoop`
on Windows. `app/db/session.py`, `app/main.py`, and `alembic/env.py` each set
`asyncio.WindowsSelectorEventLoopPolicy()` at import time (before any async
engine is created) as a guard — irrelevant on Linux/Docker, where the service
actually runs in CI and production.

## Seed data (fixed UUIDs)

`scripts/seed.py` is idempotent (safe to re-run) and creates Indian demo data —
clinics in Delhi, Pune and Bengaluru, consultation fees of ₹300–₹900, `+91` phone
numbers, state and PIN code addresses, NMC registration numbers on doctors and
placeholder 14-digit ABHA IDs on patients:

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
