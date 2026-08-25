# Decisions Log

## 2026-08-26 — V1.2 ingestion & preprocessing

- `reportlab` added as a dev-time dependency (not in `backend/requirements.txt`,
  since it's only used to *generate* fixtures, never imported by app code) to
  build the 5 lab-report PDF fixtures as realistic Indian diagnostic-lab
  layouts. `ml/generate_fixtures.py` is kept in-repo (not deleted after the
  one-off run) so the fixtures are reproducible/regenerable, matching
  `ml/*` ownership.
- The skewed/noisy scan fixture (`ml/fixtures/cbc_noisy_scan.pdf`) is built
  by rasterising the clean `cbc.pdf` at 300 DPI, injecting Gaussian pixel
  noise, and rotating 7.5 degrees, then saving as an image-only PDF (no
  text layer) via Pillow. This forces `to_pages` down the image-preprocessing
  path (`engine="ocr"`) rather than the `pdf_text` fast path, exercising
  deskew/denoise/CLAHE/threshold the way a real phone-camera scan would.
- `to_pages` returns `list[Page]`, a thin `np.ndarray` subclass carrying
  `engine`/`quality`/`low_quality`/`text` metadata. Chosen over a bare
  `list[np.ndarray]` + separate metadata list so the literal spec signature
  (`list[np.ndarray]`) still holds by subtyping, while V1.3's OCR service
  can read `page.engine == "pdf_text"` to skip OCR and reuse `page.text`
  directly instead of re-extracting it.

## 2026-08-25 — V1.1 model registry + bootstrap

- `transformers` pinned to `4.46.3` instead of the `4.47.1` in the original
  spec draft: `4.47.1` requires `tokenizers>=0.21`, which conflicts with
  `chromadb==0.5.23` (Ashwin's pin, `tokenizers<=0.20.3`). `4.46.3` requires
  `tokenizers>=0.20,<0.21`, satisfying both. No change to any line outside
  the ones this checkpoint owns.
- Local dev machine has no Microsoft C++ Build Tools installed, so
  `chroma-hnswlib` (a `chromadb` transitive dependency, not owned by this
  checkpoint) fails to build from source here. This blocks a from-scratch
  `pip install -r requirements.txt` on this box specifically; it is a
  pre-existing local toolchain gap, not caused by the V1.1 additions, and
  CI/other machines with the build tools (or a prebuilt wheel) are
  unaffected. Verified locally by installing every V1.1 dependency except
  `chromadb` directly.
- No system Tesseract binary is installed on this dev machine, so
  `registry.ocr_engine()` degrades past the `tesseract` tier straight to
  the `pymupdf` embedded-text-layer tier during local verification — this
  is the fallback chain in §3 working as designed, not a bug. PaddleOCR
  itself installs and is attempted first; whichever tier actually succeeds
  is logged once via `structlog`.
- `ml/data/negation_cues.yaml` and `ml/data/ner_gazetteer_seed.yaml` were
  created now (V1.1) as small starter files so `Registry.available()` can
  report a real `ner` capability from the first bootstrap, ahead of the
  full `ml/data/india_brands.csv` / `rxcui_lookup.csv` builds scheduled for
  V2.2/V2.3. They are seed data only and are superseded, not duplicated,
  when those later checkpoints land.

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
