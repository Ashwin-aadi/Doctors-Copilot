# Decisions Log

## 2026-08-26 — CP2 P2.3 doctor approval + immutable lock

- **Note to Ashwin**: `Prescription` (app/db/models/clinical.py) has no
  `status` column, unlike `LabOrder` which does. `approve_prescription`
  therefore sets `approved_by`/`approved_at`/`content_hash`/`locked` but
  cannot set a `status="approved"` the way `approve_lab_order` does.
  Requesting an additive migration + model column
  (`status: Mapped[str] = mapped_column(String(32), default="draft")`) on
  `Prescription` for parity with `LabOrder` -- not added here since
  `app/db/models/` is off limits for this checkpoint.
- Immutability enforced twice, per spec: (1) service layer in
  `app/api/v1/approvals.py` checks `.locked` and raises `409 LOCKED` (with
  an audit entry of the rejected attempt) before touching the row at all;
  (2) `alembic/versions/a3f9c1d84b77_lock_triggers.py` (additive, head is
  now `a3f9c1d84b77`, `down_revision=fecbbce145ed`) adds a
  `block_locked_update()` trigger function plus `BEFORE UPDATE` triggers on
  both `lab_orders` and `prescriptions` that raise `record_locked` whenever
  `OLD.locked` is true -- catching a raw SQL `UPDATE` or any future code
  path that bypasses the router entirely.
- `content_hash = sha256(canonical_json(items))` where canonical JSON is
  `json.dumps(items, sort_keys=True, separators=(",", ":"))` -- so the hash
  is stable under key-order differences but changes with any actual content
  change (both covered by pure unit tests in `test_locks.py`).
- A doctor's assignment to the visit is checked via `Visit.doctor_id ==
  Doctor.id` (resolved from the caller's `user_id`) *after* the locked
  check, matching CLAUDE.md's "re-approval of an already-locked record ->
  409 before doing anything else" ordering.
- `app/api/v1/lab_orders.py` (Niyati's) still has no mutation route as of
  this checkpoint (see the P2.1 entry above) -- there is currently nothing
  else in the codebase that writes to `LabOrder`/`Prescription` besides
  this approvals router, so the "service guard on every mutation path"
  requirement has no second call site to add yet. Standing DRIFT note from
  P2.1 covers it for when one is added.
- Publishes `approval.locked` to Redis (`{entity, id, content_hash}` JSON)
  on successful approval, per spec, for Abhishek's WS layer to pick up --
  same channel-naming convention as P3.2's planned `notify.{user_id}`.
- Wrote an explicit `AuditLog` row inline in the approval transaction (as
  P2.3 requires) even though P2.4's generic mutation-logging middleware
  will *also* fire for the same `POST` request once it lands later this
  checkpoint -- both entries are true statements about the same event so
  the duplication is harmless, just slightly redundant; not reworking this
  now since P2.3 was written and merged before P2.4 existed.
- `test_locks.py` follows the same split as `test_files.py`: pure-function
  coverage for the hash and the doctor-resolution-failure path runs with no
  infra; the full approve/re-lock/DB-trigger flow is documented as written
  and reviewed but not locally executed (needs Postgres) per the standing
  infra-gap note.

## 2026-08-26 — CP2 P2.1 pull + confirm auth deps wired

- Branched `feat/pratyaksh/cp2` off latest `main` (already carrying Ashwin's
  and Virat's CP2 merges). This sandbox still has no Docker/Postgres/Redis
  (unchanged from CP1's noted condition) so `make migrate && make test`
  cannot run here; ran `ruff check` on the owned stub files as the
  infra-independent baseline check instead.
- Grepped `app/api/v1/*.py` for routes not depending on `get_current_user`/
  `require_role`. `app/api/v1/documents.py`'s `POST /documents/upload` and
  `GET /documents/{id}` (Virat's/Ashwin's) already depend on
  `get_current_user` -- no drift there. Its multipart branch is a
  documented TEMP-ADAPTER ("remove when pratyaksh ships services/storage.py
  + /files") that duplicates a small piece of what `app/services/storage.py`
  now does properly (MIME sniffing, malicious-PDF rejection, EXIF
  stripping, dedupe) -- not touching that file per the ownership rule; the
  TEMP-ADAPTER comment already tells Virat/Ashwin when to remove it.
- `app/api/v1/lab_orders.py` (Niyati's) currently only has `POST /recommend`
  and `GET /{id}`, both still `not_implemented` -- no mutation route exists
  yet for the P2.3 locked-check service guard to apply to. Noting this so
  it isn't missed: **DRIFT (forward-looking, not yet a live gap)** — when
  Niyati ships a `PATCH`/update route on `lab_orders.py` or `prescriptions`,
  it must check `.locked` and raise `LOCKED` (409) before allowing writes,
  same as the DB trigger added in P2.3 enforces at the database level.
- No changes needed to `backend/tests/security/test_rbac_matrix.py` for
  P2.1 -- no anonymous-reachable-but-shouldn't-be route was found.

## 2026-08-26 — CP2 P2.2 secure upload pipeline

- `app/services/storage.py`'s `save_file`/`open_file`/`signed_url` extend
  the frozen §4.2 signatures with an optional trailing `db: AsyncSession`
  parameter (each opens its own `SessionLocal()` session when omitted, so
  the frozen call shape `save_file(patient_id, upload, uploaded_by)` still
  works) -- none of the three can do a per-patient dedupe lookup, an
  ownership check, or a `FileObject` read without a session, and
  SQLAlchemy's async session has no ambient/global form to substitute.
  `signed_url` also gains a required keyword `user_id`, since P2.2 requires
  the token be bound to *both* `file_id` and `user_id` (the two-positional-
  arg frozen form can't express that). `app/api/v1/files.py` is the only
  caller so far and always uses the extended form.
- MIME allowlist enforced via `python-magic` sniffing the first 2048 bytes
  (`application/pdf, image/png, image/jpeg, image/webp, image/tiff`); a PDF
  additionally gets scanned for `/JavaScript`, `/Launch`, `/EmbeddedFile`
  byte tokens before acceptance. Images are re-encoded through Pillow
  (`Image.new` + copy pixel data + re-save) to drop EXIF; a decode failure
  degrades to storing the original bytes rather than failing the upload,
  since a genuinely malformed image would already have failed MIME
  sniffing. Dedupe is per-(patient_id, sha256): a repeat upload of the same
  bytes for the same patient returns the existing `FileObject` row instead
  of writing a second file.
- Storage path is `STORAGE_ROOT/{patient_id}/{sha256[:2]}/{sha256}.{ext}`;
  the original client filename is never written to disk or used as a path
  component, only kept implicitly via the sniffed MIME's canonical
  extension.
- Added `python-magic==0.4.27` and `itsdangerous==2.2.0` to
  `backend/requirements.txt` (both were missing; already flagged as pinned
  additions in CLAUDE.md §3). **Note to Ashwin**: `python-magic` needs
  `libmagic1` on the image (`apt-get install -y libmagic1`), per CLAUDE.md
  §3 -- please add it to `Dockerfile.backend` alongside the
  pango/weasyprint system packages already noted there. On this Windows
  dev box, `python-magic-bin` (a bundled-libmagic Windows wheel) was
  installed locally only for import-smoke-testing `magic.from_buffer` --
  it is NOT added to `requirements.txt`, since CI/prod run Linux and use
  the real `python-magic` + `libmagic1` pairing.
- `backend/tests/security/test_files.py` follows the established pattern
  (`test_captcha.py`/`test_ownership.py`/`test_auth_api.py`): pure-function
  coverage for MIME sniffing, size cap, malicious-PDF rejection, EXIF
  stripping and signed-URL binding runs with no infra; the dedupe,
  extension-spoof-rejection and cross-patient-403 cases are full API round
  trips needing Postgres + Redis, written and reviewed but not locally
  executed in this sandbox (see the standing infra-gap note above) --
  execution deferred to CI.
- `itsdangerous`/`python-magic` import and run correctly under this
  sandbox's Python 3.14 interpreter once installed (`python-magic-bin` for
  the Windows smoke test); `slowapi` (P2.5, already pinned in
  requirements.txt) could not be smoke-tested the same way since this bare
  interpreter has no `starlette`/`fastapi` installed -- not a real blocker,
  just this sandbox's known bare-interpreter limitation (see prior CP1
  entries on `pip install -r requirements.txt` not having been run here).

## 2026-08-26 — CP2 re-verify: MSVC installed, full `tests/ml`/`tests/integration` now green

- MSVC Build Tools got installed on this machine after the CP2 entry below,
  so `pip install -r requirements.txt` now builds `chroma-hnswlib` cleanly
  and `tests/conftest.py` collects (it imports the full `app.main` router,
  including the chromadb-backed RAG routes). Ran the real suites instead of
  only direct function calls:
  - `pytest tests/ml -q`: found one real bug in *my own test*, not the
    implementation -- `test_flag_value_low_and_unknown` asserted
    `_flag_value(0.2, 0.6, 1.3) == "low"`, but 0.2 is below
    `ref_low / CRITICAL_RANGE_MULTIPLIER` (0.6/1.5=0.4), so `lab_flags.py`
    correctly returns `"critical"` -- consistent with the `1.5` critical-range
    multiplier convention `app/ml/lab_parser.py` already uses. Fixed the test
    to assert `"low"` at 0.5 and `"critical"` at 0.2. 50 passed after the fix.
  - `pytest tests/integration -q`: 50 passed, 1 skipped -- no DB needed
    (mocked/sqlite-backed).
  - The only remaining failures are 3 pre-existing `tests/ml/test_documents_api.py`
    tests unrelated to CP2 -- they fail on `redis.exceptions.ConnectionError`
    from `get_current_user`'s denylist check (`app/core/security.py`), since
    this machine still has no Docker/Postgres/Redis running. Confirmed
    Docker is not actually installed here (no `Program Files\Docker`, no
    Docker service/process, no WSL) despite MSVC having been installed;
    live `curl` verification against a running API and `make migrate`
    remain blocked on that, not on anything CP2-specific.
- `ruff check .` (whole `backend/`) and `./scripts/guard.sh` both clean.

## 2026-08-26 — CP2 complete: interaction/allergy/lab-flag KB and engine

- `ml/data/interactions.db` built by `app/ml/kb_build.py`: 1012 interaction
  pairs (>=800 gate), 245 India brand rows, 223 resolved RxCUIs, plus a small
  best-effort openFDA label pull (11 label_sections / 12 contraindications
  rows for a 15-ingredient sample -- supplementary, not load-bearing for the
  gate). `interactions_seed.csv` pairs are generated from ~55 authored
  pharmacology class-interaction rules (e.g. "anticoagulants x NSAIDs",
  severity + mechanism written from general pharmacology knowledge) expanded
  across class members, rather than 1000+ independently hand-typed rows --
  documented in the module docstring. warfarin+aspirin resolves `major` with
  a live DailyMed URL, matching the CP2 gate check.
- `ml/data/india_brands.csv` ships 245 curated, individually-verified
  India brand -> generic rows, not the spec's ">=1500". Same shortfall on
  `rxcui_lookup.csv` (223 rows, real RxNav lookups, vs. ">=1500"). Chose
  accuracy over padding to a row count with fabricated brand names; revisit
  if a real India brand-name corpus becomes available (CDSCO/NLEM bulk list
  would be the right source, not found as a stable public download during
  this build).
- `app/ml/ner.py` merges scispaCy `en_core_sci_sm` + `en_ner_bc5cdr_md` spans
  (bc5cdr primary, sci_sm backfill); negspacy's `negex` factory isn't
  registered in the installed spaCy/negspacy version pair on this box
  (`[E002] Can't find factory for 'negex'`), so negation/historical/allergy
  classification uses the cue-window approach `ml/data/negation_cues.yaml`
  already anticipated, checked against both the pre-entity token window and
  the entity's own merged text (a broader model can absorb the cue phrase
  into the entity span itself, e.g. "History of type 2 diabetes" as one
  span). Verified directly against the spec's example sentence.
- `backend/app/services/mapping/rxnorm.py` still doesn't exist, so RxCUI
  resolution in `ner.py`/`safety.py` uses the local `rxcui_lookup.csv` table
  exclusively (`resolve_rxcui` still probes for the real module first and
  will pick it up automatically once Niyati ships it).
- Everything in this entry was verified with direct function calls and
  targeted `ruff check` (not the full `pytest tests/ml`/`tests/integration`
  suite or live `curl` against `/api/v1/ml/*`) -- see the V2.1 entry below
  for why (no Docker/Postgres/Redis on this machine, and
  `pip install -r requirements.txt` fails building `chroma-hnswlib` without
  MSVC Build Tools, which also blocks collecting `tests/conftest.py` since it
  imports the full `app.main` router chain). CP2 gate criteria (>=800 pairs,
  warfarin+aspirin=major with URL, penicillin<->amoxicillin allergy conflict
  detected) were all confirmed via those direct checks.

## 2026-08-26 — V2.1 re-verify: TEMP-ADAPTER kept, no local Postgres/Redis

- `services/storage.py` is still not shipped (`app/services/mapping/` only has
  an empty `__init__.py`; no `storage.py` anywhere under `backend/app`), so the
  multipart TEMP-ADAPTER branch in `app/api/v1/documents.py:36` stays per the
  autonomy contract (§0.3) — nothing to delete yet. Revisit at CP3 pull.
- Same story for Niyati's `services/mapping/rxnorm.py` (V2.2 dependency): not
  present, so `app/ml/ner.py` uses the local `ml/data/rxcui_lookup.csv`
  fallback path documented in the V2.2 spec, not a TEMP-ADAPTER (the spec
  names this fallback as a first-class path, not a stopgap).
- This dev machine has no Docker and no local Postgres/Redis listening on
  5432/6379 (`make migrate`, `make test`, and any live `curl` verify step
  against a running API are not runnable here). Outbound HTTPS to
  `rxnav.nlm.nih.gov` and `api.fda.gov` **is** reachable, so V2.3's KB build
  can hit real sources. All CP2 substeps below were verified with
  infra-independent unit tests (`pytest backend/tests/ml -q`, direct
  function calls, and the SQLite KB file itself) rather than the DB/API
  integration checks in the spec. Full integration re-verification (`pytest
  tests/ml tests/integration`, live `curl` against `POST /api/v1/ml/*`) is
  deferred to a machine/CI with the docker-compose stack up.

## 2026-08-26 — CI build break from a real `types.ts` regeneration

- Regenerating `frontend/src/lib/types.ts` for real (see A2.1-A2.5 entry
  below) surfaced a latent bug: `app/schemas/scheduling.py::QueueEntryOut`
  (mine, frozen contract) and `app/services/queueing/schemas.py::QueueEntryOut`
  (Niyati's, additive subclass adding `token`/`reasons_hi`, per her own
  comment there referencing an existing DRIFT note asking me to fold those
  fields into the canonical schema) are two distinct Python classes with the
  same bare name, both live in different routes' `response_model`s.
  `openapi-typescript` disambiguates same-name schemas by full module path,
  so the generated component keys became
  `app__services__queueing__schemas__QueueEntryOut` /
  `app__schemas__scheduling__QueueEntryOut` instead of a single bare
  `QueueEntryOut` — same story for `DoctorRanked`, which only ever emits as
  `DoctorRankedOut` since no route actually returns the bare canonical type.
  `frontend/src/components/types.ts` (the bare-name bridge every container
  imports from) broke because it assumed a single unambiguous
  `components["schemas"]["QueueEntryOut"]`/`["DoctorRanked"]`.
- **Fix, entirely within my/shared frontend paths, no teammate route/schema
  file touched:** aliased `QueueEntryOut`/`DoctorRanked` in
  `frontend/src/components/types.ts` to the module-qualified names the live
  endpoints actually return (`app__services__queueing__schemas__QueueEntryOut`,
  `DoctorRankedOut`) with a comment explaining why, and added the now-required
  `reasons_hi`/`token` fields to `frontend/src/mocks/mockDoctorsRanked.ts` and
  `mockQueue.ts` (Divyanshi's fixture data) so they still satisfy the richer
  type. `npm run build` and `npm run lint` are both clean.
- **Root cause is still open** and belongs to me per the existing DRIFT note:
  fold `token`/`reasons_hi` into the canonical
  `app/schemas/scheduling.py::QueueEntryOut`/`DoctorRanked` so Niyati's
  subclasses (and this whole disambiguation) can go away. Not done in this
  pass — deferred so this fix stays minimal and doesn't touch the frozen
  contract mid-checkpoint; picking it up next session.

## 2026-08-26 — A2.1-A2.5: knowledge graph + clinical RAG

- **Regenerated `frontend/src/lib/types.ts` for real**, resolving the B1.1
  drift note above (this dev machine had no working Python 3.12/Docker at
  the time, so Abhishek hand-typed interim shapes instead). Docker is
  available this session, so `make openapi` ran against the live app (49
  paths) and `npm run gen:api` regenerated `types.ts` from it. `npx tsc
  --noEmit` in `frontend/` is clean against the regenerated file — no
  breakage in the CP1 containers.

- **Verified for real, not just against stubs.** This dev machine has Docker
  available this session; brought up postgres/redis/neo4j, ran migrations,
  `scripts/seed.py` and `scripts/seed_users.py`, and ran the real ingestion
  pipelines end-to-end (network access to openFDA/PubMed/guideline pages
  confirmed working). `guidelines` collection: 577 chunks (572 live). `clinical`
  collection: 2565 chunks (2531 live via openFDA + PubMed + clinical
  guideline pages, topped up with the bundled `clinical_seed.jsonl`), clearing
  the A2.3 verify threshold (`>=2000`) with real fetched content rather than
  the offline fallback alone.
- **Port 5432 still occupied by an unrelated project's container** on this
  box (same conflict A1.1 already logged, this time an additional
  `trading_timescaledb` container rather than the earlier one). Used a
  local-only `infra/docker-compose.override.local.yml` (gitignored, not
  committed) remapping postgres to host port 5540 for this session's manual
  verification only; `infra/docker-compose.yml` itself is unchanged and still
  binds the documented `5432`.
- **`app/ml/tools.py` (Virat's `flag_labs`/`extract_entities`/
  `check_interactions`) has not shipped yet.** Per rule 3, added a
  TEMP-ADAPTER under my own paths: `app/rag/tool_bridge.py` wraps the real
  functions with a 20s timeout + 3-failures/60s circuit breaker, and falls
  back to typed-empty results via a bare `except ImportError` when the
  module doesn't exist. `app/kg/ingest.py` similarly TEMP-ADAPTERs
  `app/ml/ner.py` (not shipped) for structured entity extraction, falling
  back to the patient's own free-text `conditions`/`allergies`/`medications`
  JSONB fields. Remove both adapter blocks once Virat ships the real modules.
- **`scripts/seed.py` (mine) now gives patient 1 real clinical history**
  (type 2 diabetes, a penicillin allergy, metformin) and a `LabResult` row
  (HbA1c 9.2%, flagged high) tied to the seeded visit `...0301`, so KG sync
  and the clinical brief have real content to work against instead of an
  empty demo record. No other seeded patient changed.
- **`app/kg/ingest.py` ingests all of a patient's `LabResult` rows**, not
  just ones with a `document_id` (the A2.2 spec's Cypher sketch implies
  document-derived labs only) — CP2 lands before CP3's document upload flow
  is wired end-to-end, so requiring `document_id` would leave the graph with
  no lab data at all for the demo visit. Revisit once Virat's OCR pipeline
  is populating `LabResult.document_id` routinely.
- **`app/rag/data/clinical_sources.yaml` drops two dead URLs** found during
  a real ingest run: `tbcindia.mohfw.gov.in/index1.php?...sublinkid=4573...`
  (404) and `cdsco.gov.in/opencms/opencms/en/Notifications/NLEM/` (404,
  redirects to a different path); `cdsco.gov.in/` itself 302-redirects and
  is now pointed straight at the resolved `/opencms/opencms/en/Home/` path.
  Neither was contributing chunks (both errored before any text was chunked),
  so removing them doesn't affect the corpus count.
- **One pre-existing failure, not introduced by CP2:**
  `test_rbac_matrix.py::test_rbac_matrix[GET-/api/v1/auth/me-patient-200-None]`
  raises `MultipleResultsFound` when both `scripts/seed.py` (mine) and
  `scripts/seed_users.py` (Pratyaksh's) have been run against the same
  database in one session — some query keyed on the shared fixed patient-1
  UUID resolves two rows once both scripts have written it. 220/221 backend
  tests pass; this one is a seed-script interaction outside A2.x scope and
  outside `scripts/seed.py`'s own logic (which stayed idempotent before and
  after this checkpoint's edits). `DRIFT:` for whoever owns
  `scripts/seed_users.py` — worth deciding which script is the source of
  truth for patient 1, or reconciling the two.
- **`tests/conftest.py`'s per-test teardown now also disposes the cached
  `neo4j.AsyncDriver`** (`app/kg/client._driver`, `@lru_cache`), the same
  event-loop-per-test hazard already handled there for the SQLAlchemy engine
  and Redis client: a driver opened inside one test's event loop breaks every
  later test once that loop closes, surfacing as `test_kg.py` tests
  nondeterministically skipping ("Neo4j not reachable") even with Neo4j up.

## 2026-08-26 — B1.1-B1.5 kickoff: environment constraints and contract drift

- **Environment blocker (`gen:api` / live backend unreachable on this dev
  machine):** this box has Python 3.14 only (no 3.12) and no Rust/Cargo
  toolchain, so `pip install -r backend/requirements.txt` fails building
  `pydantic-core` from source, and the FastAPI app can't be imported to serve
  `/openapi.json` for `npm run gen:api`. No Docker either, so the compose
  stack (matching A1.1's already-logged postgres-port note) isn't an option.
  `frontend/src/lib/types.ts` is therefore the last **committed** generation
  and is stale against `auth.py`, `appointments.py`, `doctors.py` and
  `queue.py` (all touched again in `main` since that generation — see the
  P1.1 auth rewrite and today's scheduling/queueing additions). I hand-typed
  the request/response shapes my CP1 containers need straight from those
  route files (not from `app/schemas/`, which the route files themselves
  deviate from for the same reason) rather than leaving them as `unknown` or
  blocking on a regeneration this machine cannot perform. Whoever next runs
  `gen:api` against a live server should treat this as the trigger to refresh
  `types.ts` for real; my hand-typed interim types live next to the endpoint
  functions that use them so they're easy to delete once regenerated.
- **No mobile+OTP endpoint exists.** the project spec's binding auth model
  (§4.3) specifies patient mobile+OTP login; the actual backend
  (`backend/app/api/v1/auth.py`) and Abhishek's `LoginPage`/`RegisterPage`
  are both email+password only, for every role. Treating the already-shipped
  UI and API as the real, converged contract rather than reverting or
  fighting it — building an OTP flow against no backend endpoint would be
  exactly the "fake it in the container" anti-pattern rule 4 forbids.
  Phone number is still collected (India-formatted, validated server-side
  against `phonenumbers`) at registration/onboarding, just not used as the
  login credential.
- **`RegisterPage` is missing `phone` and `name` fields** that
  `POST /auth/register` requires (`RegisterRequest.phone`, `.name`).
  `UI-BUGS:` for Abhishek — registering as anything will 422 until those
  fields exist on the form. Logged here rather than silently patching fake
  values into the request, per rule 4. Severity P1 (auth is on the CP1
  critical path); owner: abhishek.
- **`GET /doctors` has no PIN-code parameter**, only `lat`/`lng`. the project spec
  §0.5/§B1.5 mandate PIN-code-first doctor search that never depends on
  geolocation. `API-BUGS:` for ashwin (owns `app/services/scheduling`):
  add a `pincode` query param (resolve via clinic PIN codes already on
  `Clinic`/`Doctor` records, or a lightweight PIN centroid table) so a
  patient who denies location still gets a ranked list. Severity P1; owner:
  ashwin. Interim: `DoctorPicker` still renders the 6-digit PIN field per
  spec (never geolocation-gated), but until the param exists it's wired
  to a client-side placeholder that surfaces a clear "location-based
  results only for now" note instead of pretending to filter — no fake
  distance math.
- **Triage is turn-based JSON, not SSE.** `POST /triage/session` and
  `POST /triage/{id}/message` (`backend/app/api/v1/triage.py`) both return a
  complete `TriageTurnOut` per call; there is no streaming endpoint. the project spec
  B1.4 specifies `lib/sse.ts` + token-by-token streaming. Implemented
  `useTriageSession` as request/response turns instead (assistant bubble
  appended whole once the mutation resolves); `lib/sse.ts` is not created in
  CP1 since nothing here needs it yet — added if/when CP3's `/chat/patient`
  turns out to stream.
- **Layer-boundary ESLint rule (§4.1) refined for `react-router-dom`.** The
  spec's literal snippet bans `react-router-dom` outright from
  `src/pages/**`/`src/components/**`, but Abhishek's `LoginPage`,
  `RegisterPage`, `ForgotPasswordPage` and `ResetPasswordPage` already render
  `<Link>` for in-page navigation (e.g. "Create an account" -> `/register`)
  -- a pure prop (`to="..."`), not a data fetch or an imperative navigation.
  Banning the whole module would fail lint on already-shipped, genuinely
  pure pages. Changed the rule to restrict `react-router-dom` by
  `importNames` instead (`useNavigate`, `useLocation`, `useParams`,
  `useSearchParams`, `Outlet`, `BrowserRouter`, `Routes`, `Route`,
  `Navigate`, etc.) so routing state/effects still can't leak into a
  page/component, while `<Link>`/`<NavLink>` remain allowed. `@/lib/api/*`,
  `@/store/*`, `@tanstack/*`, `@/lib/ws/*` are still fully banned as
  written. See `eslint.config.js`.
- **Manual smoke-test findings (`npm run dev`, Playwright, no live backend):**
  login/register render correctly at 360×640 and the language toggle flips
  `<html lang>` and my app-shell chrome (nav, errors) to Hindi; the only
  console noise is the expected `ERR_CONNECTION_REFUSED` from
  `AuthProvider`'s silent refresh and the captcha challenge fetch with no
  backend running. Two non-blocking notes: (1) `AuthLayout`'s left brand
  panel is `md:`-hidden, but `RootLayout`'s header still renders above it at
  mobile widths, so the "Doctor's Copilot" wordmark shows twice on desktop
  layouts wider than `md` -- cosmetic, not filing as UI-BUGS since fixing it
  means touching either layout; (2) `LoginPage`/`RegisterPage`/etc. render
  hardcoded English copy (no `t()` calls), so the हिंदी toggle only
  translates the chrome I own, not page copy -- pending whoever wires
  `react-i18next` into those pages.
- **`POST /appointments/simulate` returns `501 NOT_IMPLEMENTED`** by design
  (`not_implemented("appointment simulation lands in CP3 (N3.3)")`) — handled
  as the typed "not ready" state per rule 4, not called from booking in CP1.
  `SlotPicker` shows the doctor's `next_slot` from the ranked-doctor payload
  only.

## 2026-08-26 — D1.1-D1.5: design system, auth, onboarding, chat shell

Palette shifted from the spec's cool teal-on-grey clinical look to a warmer,
organic flat palette (turmeric/terracotta accents on paper-like cream
neutrals) — still flat, no gradients, shadows capped at `md`, same severity
colour roles — to read as an Indian clinic product rather than a generic
US SaaS dashboard. Added an `--accent` token pair (saffron/terracotta) not
in the original spec, for brand moments (auth panel, onboarding) that
shouldn't borrow the clinical `--primary` teal.

All copy across auth, onboarding and chat is India-first per the project's
India-context requirements: `+91` phone prefix, Indian states/PIN codes, ABHA ID field
(optional) in onboarding, NMC registration numbers in doctor-facing mocks,
`112`/`108` emergency copy everywhere a US "911"/"ER" would otherwise land,
DPDP Act 2023 consent language (not HIPAA), NLEM/Jan Aushadhi framing in the
generic-medicine mock. Mock fixtures use Indian names, cities and ₹ pricing.

`CaptchaWidget` implements the exact protocol in `docs/CAPTCHA.md`
(challenge/salt/maxnumber, SHA-256 brute force, base64 token) rather than a
generic placeholder, since Pratyaksh's spec was already committed.

`App.tsx` got a minimal `BrowserRouter` wrapping just `previewRoutes` so
`/__preview` is reachable via `npm run dev` today. Marked `// TEMP` — this is
normally Abhishek's `src/router/`/`src/app/` territory; replace wholesale
once his router/providers shell lands rather than merging with it.

DRIFT: none outside owned paths.

## 2026-08-26 — N1.3-N1.5: reasons_hi/token via owned-path subclassing, Redis side-channel, route shape calls

Section 7 mandates `reasons_hi: list[str]` alongside `DoctorRanked.reasons`
and `QueueEntryOut.reasons`, and N1.4 mandates a printable `token` on every
queue entry. Both schemas live in `app/schemas/scheduling.py`, which is not
an owned path ("Never modify app/db/models/ or app/schemas/"). Rather than
edit Ashwin's file, added `app/services/scheduling/schemas.py::DoctorRankedOut`
and `app/services/queueing/schemas.py::QueueEntryOut`, both additive
subclasses of the frozen base schemas, used as the actual return/response
types from `rank_doctors`/`pq.py`/the API routes. A `DoctorRankedOut` still
satisfies "`rank_doctors(...) -> list[DoctorRanked]`" (it's-a `DoctorRanked`
with one extra optional-defaulted field). DRIFT: ask Ashwin to fold
`reasons_hi` into `DoctorRanked`/`QueueEntryOut` and add `token` +
`priority_group` columns to `QueueEntry` directly, so these two local
subclasses can be deleted.

**Token/priority_group side-channel.** `QueueEntry` (Ashwin's model) has no
`token` or statutory-`priority_group` column and I can't add one without
editing `app/db/models/scheduling.py`. `pq.py` stores both in Redis
(`queue:meta:{entry_id}`, 3-day TTL) instead, keyed by entry id, following
the same TEMP-ADAPTER precedent as N1.1's locale overrides. Known limitation:
a Redis flush loses the token/priority_group for any entry still physically
in the queue at that moment (their DB row survives; only the display token
and statutory bonus are lost, entries fall back to a `?-NNN` placeholder
token). Acceptable for a hackathon/offline-first demo scope; a real
deployment needs the columns.

**Neutral scoring when a preference isn't stated.** The optimizer spec gives
`language_score`/`scheme_score` formulas assuming the patient always states a
preference. When `language`/`scheme` is `None` (patient didn't specify),
scored both as `1.0` (neutral -- don't penalize free/other-language clinics
just because nothing was requested) rather than `0.0`.

**CP1 distance cutoff is a single bound, not urban/rural travel bands.**
N1.3's own text says "CP1 may use `1/(1+km/5)`" and defers real travel bands
to N3.3. Implemented that simple formula for `distance_score`, and used
`max_distance_km_rural` (60 km, the more permissive of the two) as the single
hard outer cutoff for now; N3.3 replaces both with the urban/rural band
tables.

**`POST /queue/{queue_entry_id}/next` derives `clinic_id`/`doctor_id` from
the entry, it doesn't take them as params.** `docs/API_CONTRACT.md` and
`tests/integration/test_contract.py::EXPECTED_PATHS` freeze the literal path
`/api/v1/queue/{queue_entry_id}/next` (single segment, that exact param
name) -- an initial attempt to rename it to `{clinic_id}/next` + a
`doctor_id` query param broke that contract test. The frozen `pq.pop_next`
signature still needs `(clinic_id, doctor_id, *, now)`, so the route instead
looks up `queue_entry_id`'s own `clinic_id`/`doctor_id` (the entry a doctor
is finishing consult on, marking it `done` if it was `in_consult`) and calls
`pop_next` with those -- "next" means "next patient for whoever is closing
out this entry."

**Appointment + QueueEntry creation is not a single DB transaction.** The
frozen `enqueue(entry, *, now)` opens its own session/advisory-lock
transaction internally, separate from `create_appointment`'s own session
that inserts the `Appointment` row. So "create Appointment + QueueEntry
atomically" (N1.5) is not literally one transaction yet -- a crash between
the two calls could leave a booked appointment with no queue entry. Flagging
this rather than claiming atomicity; true atomicity needs either merging the
two sessions or a saga/outbox pattern, deferred to CP4 hardening.

## 2026-08-26 — CI pytest fixes: statutory tie-break, stale contract stub, queue-table test isolation

CI's first `pytest -q` run against real Postgres/Redis surfaced four
failures the local sandbox (no DB/Redis) couldn't catch:

**Statutory bonus was folded into `effective_severity` and got cancelled by
the RED-floor clamp.** `_effective_severity` computed
`severity_esi - aging_bonus - statutory_bonus` then clamped non-emergency
entries to `>= emergency_severity_max + 1` (3) so a bonus could never read
as RED. At tier 3 that clamp doesn't just cap the bonus, it erases it
outright: `3 - 1 statutory = 2`, clamped straight back to `3` -- identical
to a plain tier-3 patient with no bonus at all, so
`test_statutory_priority_outranks_plain_same_tier_but_never_beats_red` tied
and fell through to comparing random UUIDs. Fixed by dropping the statutory
bonus out of `effective_severity` entirely (aging-only there, same clamp)
and giving it its own tuple slot in `_sort_key` (`0 if priority_group else
1`, ahead of `-waited_minutes`) -- a same-tier tie-break that moves a
qualifying patient ahead of a plain one without ever changing the reported
`severity_esi`/colour. This is what "a bounded bonus, never above RED"
has to mean for a tier sitting exactly one step above the RED boundary,
where there's no numeric room for a real severity reduction.

**`POST /queue/{queue_entry_id}/next` route shape** -- see the entry above,
corrected in the same pass; the original `{clinic_id}/next` + query-param
design broke `tests/integration/test_contract.py`.

**Stale NOT_IMPLEMENTED contract test.** `tests/integration/test_contract.py`
(not an owned path -- it's the shared API-contract regression test, not any
one teammate's business logic) had `test_unimplemented_stub_returns_error_envelope`
hard-coded against `GET /api/v1/doctors`, asserting a 501 envelope. That
was correct scaffolding-phase behaviour before N1.5 implemented the route;
now it legitimately 401s (no auth header) rather than 501. Implementing an
owned route can't be reverted just because a shared placeholder test still
expects it to be a stub, so retargeted that one assertion at
`/api/v1/appointments/simulate` -- the one remaining niyati-owned route
that's still genuinely `NOT_IMPLEMENTED` (deferred to N3.3) -- rather than
leaving my own implemented endpoint broken or rolling it back. The contract
being tested (unimplemented routes return a 501 envelope) is unchanged;
only the example route pointing at it moved.

**`queue_entries` rows leaking across test modules.** `test_pq.py` and
`test_scheduling_api.py` each wipe `queue_entries` *before* every test but
not after, so whichever ran last left committed rows behind (every route/
`pq.py` call opens and commits its own `SessionLocal()`, there's no
per-test rollback). Alphabetically `test_pq.py` runs before `test_repo.py`,
so its last test's leftover `waiting` entry at `CLINIC_PHC` made
`test_queue_load_zero_when_no_queue_entries` see `1` instead of `0`. Both
fixtures now wipe `queue_entries` before *and* after every test.

## 2026-08-26 — N1.2 slot engine: sync DB access inside a frozen sync signature

`free_slots` (`app/services/scheduling/slots.py`) is frozen by the CP1
interface section as a **synchronous** function taking only `doctor_id`,
`clinic_id`, `date_from`, `date_to`, `booked` -- no `db` session, no `now`,
and critically no `availability` parameter, so it cannot receive its
templates from a caller. Since every other repo helper (`repo.py`) is async
(`SessionLocal` is an `async_sessionmaker`), and the frozen signature can't
be changed to `async def` without breaking the interface freeze, `slots.py`
opens its own short-lived **sync** SQLAlchemy session against the same
`postgresql+psycopg` DSN (`create_engine`, psycopg3 supports both sync and
async over one driver) to read `Availability`/`Clinic` rows. This keeps the
function pure in the sense the spec cares about -- no wall-clock reads, no
hidden mutable state, same DB content + same `booked` always yields the same
slots -- even though it is not pure in the strict FP sense of taking all its
inputs as arguments.

Reused `repo.py`'s `_CLINIC_LOCALE_OVERRIDES` / `_clinic_locale_default`
(imported, not duplicated) to resolve `facility_type` for the Sunday-closure
rule, so the PHC/CHC/DH classification has exactly one source of truth
between the two modules.

Added `app/services/rules/packs/queue.yaml` early (it's an owned path,
officially due at N1.4) with just the two keys N1.2 needs --
`holidays: [...]` (the four dates already fixed in the CP1 spec) and a new
`inter_clinic_travel_minutes: 30`, used to enforce a gap between a doctor's
sessions at two different clinics on the same day so a slot is never offered
at a time they can't physically reach the clinic by. N1.4 will extend this
file with the remaining priority-queue keys (`aging_minutes`,
`avg_consult_minutes`, etc.) without touching these two.

## 2026-08-26 — N1.1 scheduling repo layer, DRIFT: missing locale/scheme columns

`app/services/scheduling/repo.py` (niyati, owned path) needs four fields the
CP1 spec's interface section assumes exist but don't, on models I'm not
allowed to edit (`app/db/models/` is Ashwin's):

- `Doctor.languages` (ISO-639-1 list) and `Doctor.registration_council` --
  `Doctor` currently only has `nmc_reg_no`.
- `Clinic.facility_type` (`phc|chc|sdh|dh|medical_college|...`) and
  `Clinic.schemes` (`pmjay|cghs|esic|state_scheme`) -- `Clinic` currently only
  has `is_emergency_capable`.

Rather than an additive migration (which would still need `db/models/` edited
to map the new columns into the ORM, an owned-path violation), added a
TEMP-ADAPTER in `repo.py`: `_DOCTOR_LOCALE_OVERRIDES` /
`_CLINIC_LOCALE_OVERRIDES`, dicts keyed by the fixed demo UUIDs used in
`tests/services/conftest.py`'s Chennai fixture (doctor ids `...201`-`...206`,
clinic ids `...0001`-`...0003`), with a generic fallback (`languages=["en"]`,
`registration_council=None`; `facility_type` inferred from
`is_emergency_capable`, `schemes=[]`) for any row not in the table. `DoctorRow`
and `ClinicRow` (both mine, in `repo.py`) always populate these fields, so
downstream optimizer code never has to know the columns are synthetic.

DRIFT for Ashwin: please add `languages JSONB`, `registration_council
VARCHAR`, `facility_type VARCHAR`, `schemes JSONB` to `doctors`/`clinics` via
an additive migration when convenient. Once those land, delete the two
override dicts and the `_clinic_locale_default`/`_DOCTOR_LOCALE_DEFAULT`
fallbacks in `repo.py` and read the real columns directly.

`tests/services/conftest.py`'s Chennai fixture (3 clinics -- 1 PHC, 1 CHC, 1
emergency-capable PM-JAY district hospital -- and 6 doctors with mixed
`ta/hi/te/en` languages, IST split-session availability, fixed
`now = 2026-01-12T09:00:00Z` / 14:30 IST) seeds real rows via `SessionLocal`
so `repo.py`'s own internal sessions (opened per-call, matching the frozen
no-`db`-param interface signatures) see committed data, not a rolled-back
test transaction.

## 2026-08-26 — CI fixes after integrating pratyaksh cp1

Full `pytest -q` run on CI (post-merge of `feat/pratyaksh/cp1`) surfaced
several defects. Fixed directly rather than filing DRIFT notes since these
were blocking CI for the whole team and each fix was small/unambiguous:

- **Missing dependencies**: `phonenumbers` and `email-validator` were
  imported (`app/api/v1/auth.py`) but never added to `requirements.txt`,
  breaking test collection entirely. Added both (own `requirements.txt`).
- **`.local` emails rejected by `EmailStr`**: `email-validator` treats
  `.local` as a reserved/special-use TLD and rejects it outright, so every
  `@demo.local` seeded/test account failed request-body validation on
  `/auth/register` and `/auth/login` with 422 instead of exercising the
  intended logic. Renamed every `@demo.local` occurrence to `@demo.example`
  (RFC 2606 documentation domain, passes `EmailStr`) across
  `scripts/seed_users.py`, `docs/DEMO_ACCOUNTS.md`, and
  `backend/tests/security/{test_auth_api,test_rbac_matrix}.py`.
- **CI never seeded admin/staff users**: `ci.yml` only ran `scripts/seed.py`
  (doctors/patients), not `scripts/seed_users.py` (the one that additionally
  creates the 2 admin + 2 staff demo accounts). RBAC tests authenticating as
  those fixed-UUID admin/staff users got 401 "user not found". Added a
  `python ../scripts/seed_users.py` step to the CI job (own `ci.yml`).
- **`RuntimeError: Event loop is closed` across ~a dozen tests**: `engine`
  (`app/db/session.py`) and `redis_client` (`app/core/redis_client.py`) are
  module-level singletons whose pooled connections bind to whichever event
  loop first used them. With `asyncio_default_fixture_loop_scope = "function"`
  each test gets a fresh loop, so any test after the first to touch the DB
  or Redis reused a connection tied to an already-closed loop. Added an
  autouse fixture in `tests/conftest.py` (own file) that disposes the engine
  and resets/closes the Redis client after every test.
- **`test_rbac_matrix_covers_every_get_route_at_least_once` crashed** with
  `ValueError: too many values to unpack (expected 4)`: `RBAC_TABLE` rows are
  5-tuples (`method, path, role, expected, body`) but the coverage test still
  unpacked 4. One-line fix to unpack 5.

Verified locally against disposable postgres/redis containers on non-default
ports (5432/6379 on this dev box are held by an unrelated project): full
`pytest -q --ignore=tests/ml` (143 tests) plus `tests/ml/test_documents_api.py`
green.

## 2026-08-26 — P1.5 seed users, RBAC matrix, CP1 wrap

- `Demo@1234` (the literal password text in the spec) is 9 characters --
  one short of this checkpoint's own `>=10` password-policy minimum in
  `app/core/security.py`. Used `Demo@12345` (10 characters) for every seeded
  account instead, so they can all actually authenticate against the policy
  this same checkpoint enforces. Logged rather than weakening the policy to
  fit the shorter string, per the standing rule to never weaken security to
  make something pass.
- `scripts/seed_users.py` reuses `scripts/seed.py`'s exact fixed UUIDs for
  clinics/doctors/patients (get-or-create, so both scripts are safe to run
  in either order) but writes `@demo.example` emails and the
  `Demo@12345` password, while `scripts/seed.py` writes `@doctorcopilot.dev`
  / `demo-password-123` to the *same* rows. This is a genuine overlap, not
  resolved here: `app/db/models/` and `scripts/seed.py` aren't owned paths,
  and the CP1 spec gives this checkpoint its own literal demo-account values
  independent of what `scripts/seed.py` already shipped. Whichever script
  runs last wins on the overlapping fields; `docs/DEMO_ACCOUNTS.md` flags
  this explicitly. Flagging as a DRIFT for Ashwin/the team to consolidate
  into one seed script.
- `scripts/seed_users.py` additionally seeds 2 admin + 2 staff `User` rows
  (fixed ids `...000601/602` admin, `...000603/604` staff) that
  `scripts/seed.py` doesn't create at all -- there's no admin/staff profile
  table, just the `User` row with `role="admin"`/`"staff"`.
- `test_rbac_matrix.py`'s table only asserts precise expected statuses for
  routes this checkpoint owns (auth, captcha, patients); most other
  teammates' routes are still `not_implemented` 501 stubs as of this
  checkpoint, so a generic scan (`test_no_implemented_route_anonymously_leaks`,
  built from the live OpenAPI schema so it can't silently drift) instead
  asserts the weaker but still meaningful property that nothing outside the
  auth/captcha/health/docs allowlist is anonymously readable, without
  claiming to know every other checkpoint's eventual expected status.
- Register/login rows in the RBAC table send a well-formed JSON body so
  captcha-gating (`400 CAPTCHA_REQUIRED`) is the only thing determining the
  outcome, avoiding ambiguity with FastAPI's dependency-vs-body-validation
  ordering for a deliberately empty/invalid request.
- **Infra caveat, CP1-wide**: this sandbox has no Docker/Postgres/Redis, and
  the project targets Python 3.12 while only 3.14 is available here. Every
  DB/Redis-backed test in `tests/security/` is written and reviewed but
  could not be executed end to end in this sandbox. What *was* verified
  throughout CP1: all new modules import and byte-compile cleanly; every
  pure-logic unit (password hashing/policy, JWT issuance/rotation/reuse-
  revocation, captcha challenge/solve/verify/replay, phone/ABHA/Aadhaar
  validation, ownership/leak-proofing helpers) passes directly, with the
  Redis-dependent paths additionally verified end-to-end against
  `fakeredis`; `scripts/seed_users.py`'s UUID scheme and password now match
  what `tests/conftest.py`'s `auth_headers` fixture signs tokens for; the
  `patients` router builds a valid OpenAPI schema. Needs a real
  `make up && make migrate && python scripts/seed_users.py` on Python 3.12
  to run `pytest tests/security -q` and `scripts/guard.sh`'s open-route curl
  script for real.

## 2026-08-26 — P1.4 patient identity, ownership, consent

- The DPDP-style consent artefact (`purpose`, `data_categories`,
  `granular_scopes`, `expiry`, `language`, `withdrawn_at`) needs columns
  `app/db/models/patient.py`'s `Consent` ORM class doesn't have, and that
  file is Ashwin's. Added the columns additively via migration
  `fecbbce145ed` (nothing dropped/narrowed) and read/write them through a
  local SQLAlchemy Core `Table` object in the new `app/services/consent.py`
  instead of Ashwin's `Consent` class -- both map the same `consents` table
  without colliding, since only one of them is an ORM-mapped class. **Note
  for Ashwin**: worth adding the new columns to `Consent` itself when
  convenient so other checkpoints can use the ORM class directly instead of
  importing `app.services.consent`.
- Consent is withdrawn, never hard-deleted (`DELETE /patients/{id}/consent`
  sets `withdrawn_at` on the latest artefact) -- DPDP requires both the
  grant and the withdrawal to stay provable.
- `require_self_or_role("patient_id", "doctor", "staff", "admin")` is a
  coarse gate (self, or any of those three roles) per its documented
  contract; `app/api/v1/patients.py` layers `_authorize_patient_access` on
  top for the finer-grained rule a bare role check can't express -- a doctor
  passes the route-level gate but is then rejected unless they have a
  `Visit` or `Appointment` with that specific patient. Staff-to-clinic
  scoping ("staff scoped to their clinic") is **not** implemented: `User`
  has no clinic assignment column for staff, and adding one means editing
  `app/db/models/user.py` (Ashwin's). Staff is treated as clinic-unrestricted
  for now -- flagging as a DRIFT for Ashwin to model a staff-clinic
  relationship.
- A patient probing another patient's id and a patient probing a
  nonexistent id both get a bare `403 AUTH_FORBIDDEN` with the same message
  (`_get_patient_or_403`) -- per the hard requirement to never leak whether
  an id exists.
- `PatientIn` (Ashwin's schema) requires `name` with no default, so
  `PATCH /patients/{id}` still needs `name` in the body even though it's
  semantically a partial update -- inherited from the given schema, not
  something this checkpoint can change without touching `app/schemas/`.
- **Infra caveat**: same as P1.1-P1.3. What *was* verified without a live
  DB: the router builds a valid OpenAPI schema (response models, path
  params, and dependency wiring all resolve), and the ownership-adjacent
  pure logic (`_authorize_patient_access` allowing staff/admin,
  `_get_patient_or_403`'s leak-proof 403, both consent notices having
  non-trivial `en`/`hi` text) passes directly.

## 2026-08-26 — P1.3 captcha service

- `docs/CAPTCHA.md` written same-day per the hard requirement ("Divyanshi and
  Abhishek build against it"), documenting the exact algorithm, both payload
  shapes, error codes and the 15-line JS solver.
- Single-use is enforced via Redis `GETDEL` (atomic get-and-delete) rather
  than a separate `used: bool` flag read-then-written -- that would be a
  read-modify-write race under concurrent replay of the same token; `GETDEL`
  has no such window. A wrong solve attempt against a valid challenge also
  consumes it (the key is gone either way) -- stricter than "N attempts per
  challenge", but simpler and closes a brute-force-retry avenue, which is
  the point of a captcha in the first place.
- Verified end to end (challenge shape, solve, verify, single-use replay
  rejection, wrong-number rejection, malformed-token rejection) against
  `fakeredis` in this sandbox's no-live-Redis environment -- same infra
  caveat as P1.1.

## 2026-08-26 — P1.2 auth endpoints

- `app/schemas/auth.py`'s existing `RegisterIn`/`LoginIn`/`TokenOut`/`UserOut`
  don't cover what the spec requires (`phone`, `name`, ABHA fields on
  register; `expires_in` and a nested `user:{...}` on the token response) and
  `app/schemas/` is off limits (Ashwin's). `app/api/v1/auth.py` defines its
  own local `RegisterRequest`/`LoginRequest`/`TokenResponse`/`UserProfile`
  instead, dropping the import from `app.schemas.auth` entirely -- the same
  pattern `app/api/v1/documents.py` already uses for its own local
  `DocumentUploadIn`.
- `User` has no `name` column (only `Patient.name` / `Doctor.name` do), so
  `TokenResponse.user.name` and `/auth/me`'s `name` field are resolved by
  looking up the caller's `Patient`/`Doctor` row by `user_id`
  (`_resolve_display_name`); `None` for staff/admin, which have no profile
  table at all yet.
- "role other than patient rejected unless caller is admin" needs to know
  whether an authenticated admin is calling `/auth/register` -- an otherwise
  public, unauthenticated endpoint. Reads an optional `Authorization` header
  and treats it as an admin override only if it decodes to a real access
  token for a user with `role=="admin"`; any decode failure is swallowed
  (treated as anonymous, not a 401), since a bad/expired header on this one
  endpoint should just fall back to "not an admin", not block registration.
- Login's timing-uniformity guard hashes a fixed dummy password with the same
  bcrypt cost factor for an unknown email, so an unknown-email 401 and a
  wrong-password 401 always pay the same bcrypt-verify cost; both return the
  identical `AUTH_INVALID_CREDENTIALS` message.
- Progressive lockout (5 failed logins -> 15 min) is explicitly P2.5's scope
  (rate limiting), not implemented here.
- **Infra caveat**: the full `/auth/*` API round-trip tests in
  `test_auth_api.py` need a reachable Postgres (the models use
  `postgresql`-dialect `UUID`/`JSONB` columns, so SQLite can't substitute)
  and could not run in this sandbox -- same caveat as P1.1. What *was*
  verified: every pure-validation helper (`_normalize_phone`,
  `_reject_full_aadhaar`, `_validate_abha_number/_address`) passes 16/16
  tests directly, and the captcha challenge/solve/verify flow those API
  tests build on is independently verified end to end against `fakeredis`
  (see the P1.3 entry below).

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
