# Doctor's Copilot

Clinic platform: RAG-based patient triage and doctor booking, lab report OCR, a
patient knowledge graph, and a cited clinical brief for the treating doctor —
grounded in FDA labels and public guidelines, with drug-interaction and allergy
checks and every clinical approval locked behind doctor signature + captcha.

Full quickstart and architecture docs land at the end of the build in
`docs/ARCHITECTURE.md` and `docs/DEMO_SCRIPT.md`.

## Quickstart (dev)

```bash
cp .env.example .env
make up        # postgres, redis, neo4j
make install   # backend + frontend deps
make migrate
make seed      # demo clinics/doctors/patients, fixed UUIDs — see docs/ARCHITECTURE.md
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
