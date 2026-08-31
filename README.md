# Doctor's Copilot

A clinic platform for **Indian primary and secondary care**: RAG-based patient
triage and doctor booking, lab report OCR, a patient knowledge graph, and a cited
clinical brief for the treating doctor — with drug-interaction and allergy checks
and every clinical approval locked behind doctor signature + captcha.

An Indian OPD runs on long queues, uneven specialist access, paper lab reports and
out-of-pocket drug costs. This system is built around those constraints rather than
adapted to them:

- **Grounded in Indian guidance first.** Retrieval prefers MoHFW, NCVBDC, NTEP,
  NCDC, ICMR and NHM material, plus WHO coverage of the communicable and tropical
  burden that actually fills Indian OPDs — dengue, malaria, chikungunya, enteric
  fever, tuberculosis, scrub typhus, leptospirosis, snakebite, rheumatic heart
  disease. International drug labels stay in the loop as pharmacology backbone,
  never as the primary voice on first-line management.
- **Triage in the local idiom.** Severity is carried as ESI 1–5 *and* as the
  MoHFW/AIIMS casualty colour — red, yellow, green — which is what triage counters
  and queue boards run on. Red-flag detection covers dengue warning signs,
  snakebite envenoming, pesticide poisoning, heat stroke, febrile seizures and
  obstetric bleeding alongside the universal emergencies.
- **Affordable prescribing.** Medication suggestions are checked against the
  National List of Essential Medicines and flagged when a Jan Aushadhi generic
  exists, with indicative ₹ MRP.
- **ABDM-ready.** Patients carry an optional ABHA ID, doctors an NMC registration
  number. Consent and retention follow the DPDP Act 2023.

Emergency guidance in the product cites **112**, or **108** for an ambulance.

Full quickstart and architecture docs land at the end of the build in
`docs/ARCHITECTURE.md` and `docs/DEMO_SCRIPT.md`.

## Quickstart (dev)

```bash
cp .env.example .env
make up        # postgres, redis, neo4j
make install   # backend + frontend deps
make migrate
make seed      # Indian demo clinics/doctors/patients, fixed UUIDs — see docs/ARCHITECTURE.md
make api       # backend on :8000
make web       # frontend on :5173
```

Set `GROQ_API_KEY` in `.env` for live LLM responses (free tier at
console.groq.com). Without it the LLM gateway falls back to a local Ollama
instance, then to a deterministic extractive summary — every endpoint stays
up, just with lower-quality generated text until a key or local model is
configured.

Run `make smoke` after the stack is up to exercise `/health`, the OpenAPI
contract surface, and a full pre-assessment triage session end to end.

## Deploy

The whole stack runs in containers behind nginx, with one command:

```bash
cp .env.example .env          # set SECRET_KEY and GROQ_API_KEY
make prod-up                  # build and start everything
./scripts/deploy_check.sh     # assert it is actually serving
make prod-seed                # demo data
```

Web app on :80, API on :8000; override with `WEB_HOST_PORT` / `API_HOST_PORT`.
Migrations are applied by the container on start. See `docs/DEPLOYMENT.md` for
volumes, troubleshooting and what to change before exposing it publicly.
