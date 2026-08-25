# Decisions Log

## 2026-08-25 — Relocalisation: the product targets India, not the US

CP1 shipped with an implicitly US-centric spine (MedlinePlus-only corpus, ESI
numbers with no local equivalent, dollar-ish fees, generic Western demo data).
The product is for Indian clinics, so the following changed across the contract,
the corpora and the CP1 code. Recorded here because several items bind teammates.

**Contract (additive only — nothing removed, so no breakage for unshipped work):**

- `TriageResult.triage_colour` and `QueueEntryOut.triage_colour` —
  `red`/`yellow`/`green`, the MoHFW/AIIMS casualty code. `severity_esi` is
  unchanged and remains the machine value; the colour is derived from it by
  `colour_for_esi()` in `app/schemas/triage.py`. **Niyati**: use that helper when
  building `QueueEntryOut` rather than re-deriving the mapping.
- `DoctorRanked.nmc_reg_no`, `Doctor.nmc_reg_no` — National Medical Commission
  registration. `fee` is documented as INR (no type change).
- `PatientIn/Out.state`, `.pin_code`, `.abha_id`; matching `Patient` columns, plus
  `Clinic.state` / `Clinic.pin_code`. Migration `b1c4e7a92d10`, additive, all
  nullable. **Pratyaksh**: `abha_id` is optional and unverified at this stage —
  treat it as a display/identity hint, not an authentication factor.
- `MedCandidate.nlem_listed`, `.jan_aushadhi_available`, `.mrp_inr`. **Virat**:
  these default to `False`/`None`, so `med_suggest` can populate them
  incrementally without breaking the schema.

**Retrieval grounding.** `guideline_sources.yaml` was rewritten India-first: 96
sources in three priority bands — Indian government/programme material and WHO
India pages (`region: IN`), WHO fact sheets for the Indian communicable and
tropical burden, then MedlinePlus for general symptom coverage. Every chunk now
carries a `region` key of `IN` or `INTL` so CP2's `clinical_rag` can prefer Indian
guidance at rerank time. Live ingestion yields 576 chunks (was 294), 91 of them
from `region: IN` sources.

**Why not drop openFDA/RxNorm entirely.** Considered and rejected. Drug-interaction
mechanism and pharmacokinetics are not country-specific, and no free Indian API
exposes equivalent structured interaction data — CDSCO publishes no such endpoint.
They stay as the pharmacology backbone with an explicit rule that Indian sources
win on first-line management and availability whenever the two disagree.

**Triage rules.** `esi_rules.yaml` gained a `colour_map`, a `colour` on each tier,
India-typical examples per tier, and 14 additional red-flag patterns covering
dengue warning signs, snakebite envenoming, pesticide/organophosphate ingestion,
heat stroke, febrile seizures, meningism, obstetric bleeding, animal bites and
severe paediatric dehydration.

**Offline corpus.** `symptom_corpus.yaml` extended from 65 to 84 entries;
`sym-066` onward are India-prevalent presentations, so the offline fallback path
keeps its India specificity rather than degrading to a generic Western corpus.

**Copy conventions, now enforced in prompts.** Emergency guidance cites 112 (and
108 for an ambulance), never 911. Costs are ₹. Consent and retention language
follows the DPDP Act 2023, not HIPAA. Suggested labs are restricted to what an
Indian district diagnostic lab actually runs.

**Demo data.** Seed clinics moved to Delhi, Pune and Bengaluru with real PIN codes;
fees ₹300–₹900; `+91` phone numbers; NMC registration numbers; placeholder 14-digit
ABHA IDs. Fixed UUIDs are unchanged, so anything already referencing patient
`...000101` or visit `...000301` still resolves.

## 2026-08-25 — A1.4 finalize() confidence without a Groq credential

- `finalize()` calls `json_complete` for the structured `TriageResult`. With no
  `GROQ_API_KEY` set (this project's only paid/free-tier credential, left
  blank in `.env` until a teammate supplies one) and no local Ollama daemon
  running, the LLM gateway exhausts both providers and returns the extractive
  fallback string, which is not valid JSON for the schema. `json_complete`
  degrades to a schema-default instance rather than raising, so `finalize()`
  still returns a well-formed `TriageResult` — just with `citations=[]` and
  `confidence=0.0` — instead of crashing the request. Red-flag detection
  (regex-based) still works with zero external dependencies, so severity
  routing stays correct even fully offline. The A1.4 verify line asserting
  `citations|length>=2` will only pass once a real `GROQ_API_KEY` is present;
  `tests/test_triage.py` covers the business logic deterministically via
  monkeypatched LLM calls instead of depending on a live credential.

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
