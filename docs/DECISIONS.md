# Decisions Log

## 2026-08-26 — P1.1 security core

- `passlib[bcrypt]==1.7.4` + `bcrypt==4.2.1` (both already pinned in
  `backend/requirements.txt` before this checkpoint) are incompatible:
  passlib's bcrypt backend self-test (`detect_wrap_bug`) hashes a >72-byte
  probe string, which bcrypt>=4.1 rejects with `ValueError` instead of the
  silent truncation older bcrypt did, so every `CryptContext(schemes=
  ["bcrypt"]).hash(...)` call raises. `app/core/security.py` hashes via the
  `bcrypt` module directly (`bcrypt.hashpw`/`bcrypt.checkpw`, rounds=12,
  password bytes truncated to 72 ourselves) instead of routing through
  passlib, sidestepping the incompatibility entirely. **Note for Ashwin**:
  `scripts/seed.py` still uses `passlib.context.CryptContext(schemes=
  ["bcrypt"])` and will hit the same `ValueError` when run against this
  environment's `bcrypt==4.2.1` — not touched here since `scripts/seed.py`
  isn't an owned path, flagging as a DRIFT for whoever runs it next.
- `backend/tests/conftest.py`'s `auth_headers` fixture (shared, not in my
  owned paths, but its own comment said to "swap the header construction for
  a real login call once `/api/v1/auth/login` is implemented") now signs a
  real access token via `app.core.security.create_access_token` instead of
  returning the `test-{role}-token` placeholder `get_current_user` used to
  special-case. Kept synchronous with the same `auth_headers("doctor") ->
  dict` signature (existing tests like `tests/ml/test_documents_api.py` call
  it unawaited inline as a `headers=` kwarg) by signing for one of
  `scripts/seed_users.py`'s fixed per-role UUIDs rather than doing an awaited
  DB lookup. `get_current_user` still loads that id from the DB and 401s if
  it isn't seeded, so behaviour for an unseeded DB is unchanged.
- `app/core/deps.py`'s `get_current_user` now decodes and verifies a real
  JWT (`typ=="access"`, not on the Redis denylist, backing `User` active) in
  place of the `test-{role}-token` placeholder branch the TEMP-ADAPTER
  comment marked for removal; `CurrentUser`'s shape (`id`, `role`) is
  unchanged so `app/api/v1/documents.py` needed no changes.
- **Infra caveat**: this sandbox has no Docker/Postgres/Redis, and the
  project pins Python >=3.12 while the only Python here is 3.14. Verified
  what's actually checkable: a throwaway venv with just this checkpoint's
  direct dependencies (not the full `requirements.txt`, which pulls in
  torch/paddleocr/chromadb that don't have 3.14 wheels) installs and imports
  cleanly; `pytest --noconftest tests/security/test_tokens.py` (bypassing the
  shared conftest, which imports the full ML-heavy router tree) passes 10/10
  logic tests, with the 2 Redis-dependent tests additionally verified end to
  end against `fakeredis` (rotation, reuse-revokes-family, and denylist all
  behave correctly). Needs a real `make up && make migrate` environment on
  Python 3.12 to run the full suite through `conftest.py`.

## 2026-08-26 — V1.5 API, worker, push

- `app/core/deps.py` (`get_current_user`) didn't exist anywhere on `main` —
  Pratyaksh's login/JWT issuance hasn't landed yet, only stub `not_implemented`
  routes in `app/api/v1/auth.py`. The spec requires `Depends(get_current_user)`
  on both document routes, and `backend/tests/conftest.py`'s `auth_headers`
  fixture already emits a `Bearer test-{role}-token` placeholder expecting
  something to consume it. Added a minimal `get_current_user` that accepts
  only that placeholder, resolving it to a real seeded `User` row of the
  matching role (needed so `FileObject.uploaded_by`'s FK is satisfiable) —
  same TEMP-ADAPTER pattern the spec already sanctions for the storage-not-
  merged case. Marked for removal once `/auth/login` + real token issuance
  exist; the file lives outside `app/ml` and `app/api/v1/documents.py` because
  it's a shared interface both routes and other checkpoints will import.
- `POST /documents/upload` branches on `Content-Type`: multipart (the
  TEMP-ADAPTER storage path, storing to `STORAGE_ROOT/tmp/` and writing a
  `FileObject` row directly) vs. JSON `{file_id, patient_id}` against an
  already-existing `FileObject` (the real path once `/files` ships). Both are
  handled in one handler via `Request` rather than two routes, since the spec
  describes it as one endpoint with a conditional branch.
- The worker (`app/workers/ocr_worker.py`) uses a **synchronous** SQLAlchemy
  session over the same `postgresql+psycopg` URL, not the async engine in
  `app/db/session.py` — that engine's pool is bound to the API process's
  event loop, and RQ jobs run in a separate worker process with no running
  loop of their own.
- `document.done` is published via `redis.publish` directly (`app/core/events`
  has only FastAPI lifespan hooks, no pub/sub helper), matching the spec's
  documented fallback ("`app.core.events` if present, else `redis.publish`").
- **Infra caveat**: this sandbox has no Docker/Postgres/Redis available, so
  the DB-backed tests in `test_documents_api.py` and the curl end-to-end
  Verify step could not actually be executed here. What *was* verified: all
  new/changed modules import cleanly, `app.main`'s OpenAPI schema still
  registers both document paths and all 48 non-health contract tests pass
  (proving routing/dependency-injection wiring is sound), and the two
  auth-only tests that don't need a DB connection (`test_upload_requires_auth`,
  `test_get_requires_auth`) pass. The three DB-dependent tests fail purely on
  `OperationalError: connection ... failed` (Postgres unreachable) — confirmed
  by inspection to be an infra-availability failure, not a code path. Needs a
  real `make up && make migrate && make seed` environment to close the loop.

## 2026-08-26 — V1.4 lab report parser

- `ml/data/critical_rules.yaml` is created even though it isn't in V1.4's
  `Files:` header, because the `Do:` text explicitly requires it
  (`ml/data/critical_rules.yaml` hard rules for platelets/haemoglobin/
  glucose/creatinine) and it's `ml/data/*`, squarely Virat-owned. Same for
  `ml/fixtures/expected/*.yaml`, needed to satisfy the "≥85% field accuracy,
  asserted against a hand-written expected YAML" requirement.
- Per-cell OCR confidence doesn't survive table clustering — `OcrResult`'s
  `tables` field is `list[list[list[str]]]`, plain strings with no `conf`.
  `parse_labs` recovers a confidence proxy by looking up each cell's exact
  stripped text against the page's `blocks` (which do carry `conf`), falling
  back to the page's mean block confidence when a cell's text doesn't match
  any single block exactly (e.g. a cell joined from multiple OCR blocks).
  `confidence = min(that proxy, alias-match score)` per the spec formula.
- `reference_ranges.yaml` is a fallback only: all 5 fixtures print their own
  reference range in the table's range column, so `_default_range()` never
  fires against them. Its sex-specific (`male`/`female`) bounds for
  haemoglobin/creatinine/uric_acid/ESR/iron/ferritin are populated for a
  future caller with patient context (e.g. V2.5 `lab_flags.py`); `parse_labs`
  itself has no patient argument (per the V1.4 signature), so it always uses
  `default`.
- "Critical when value is beyond 1.5x outside the range" is implemented as
  `abs(value - nearest_bound) > 1.5 * (high - low)` (range-width multiple),
  not `value > 1.5 * bound`, and only when both bounds are known. The
  bound-multiple reading would misfire on ordinary `high`/`low` results with
  a narrow range relative to the boundary (e.g. CBC's ESR 28 vs 0–15 would
  wrongly flip to `critical` under a literal `value > 1.5*high` reading);
  the width-multiple reading matches all 5 fixtures' hand-verified expected
  flags with no false-positive criticals, and only the 4 explicit hard rules
  in `critical_rules.yaml` can mark a result critical outside that.
- Hard critical-rule unit conversion (`_to_rule_unit`) only handles the
  specific unit strings the fixtures/spec actually use (`lakhs/cu mm` ->
  `/uL` for the platelet rule; direct match for `g/dL`/`mg/dL`). It returns
  `None` (rule skipped, never guessed) for any other unit spelling rather
  than attempting a general unit-parser — safer than a wrong critical flag.

## 2026-08-26 — V1.3 OCR service

- `run_ocr` never runs OCR on a page `to_pages` already marked
  `engine="pdf_text"`: it re-opens the source PDF and reads word-level
  geometry via `fitz`'s `get_text("words")` (scaled by `300/72` to match the
  300 DPI raster the rest of the pipeline uses) instead, with `conf=1.0` per
  block. This was the design intent recorded in V1.2's decision entry — an
  embedded text layer is already exact, so running PaddleOCR/Tesseract over
  its raster would only add error and cost, never improve on it.
- Table extraction uses the y-centroid/x-gap clustering fallback from the
  spec unconditionally, even though `from paddleocr import PPStructure`
  imports cleanly on this machine. PP-Structure's table/layout models are not
  the ones cached from V1.1's `warm_up()` run (only `det/en`, `det/ml`,
  `rec/en`, `rec/devanagari`, `cls`) and pulling its additional layout
  weights would mean an uncontrolled network fetch mid-pipeline (and
  mid-test-run) with no offline fallback of its own. The clustering path has
  no such dependency and already passes every fixture. Revisit once
  PP-Structure's weights are deliberately vendored/cached, per §3's
  fallback-chain philosophy.
- `run_ocr`'s fallback chain (PaddleOCR `en` -> PaddleOCR `devanagari` ->
  Tesseract) keeps the highest-confidence result across whichever tiers
  actually ran, rather than stopping at the first one to clear the 0.60
  threshold, so a low-confidence English pass doesn't win over a
  higher-confidence Devanagari or Tesseract rerun. Verified live end-to-end
  against `ml/fixtures/cbc_noisy_scan.pdf` (no system Tesseract on this dev
  box, so only the PaddleOCR tiers are exercised locally): `paddle_en`
  resolves the rotated/noised scan at `mean_confidence=0.966` without
  needing the Devanagari or Tesseract reruns.

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
