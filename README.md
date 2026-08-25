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
make up
make install
make migrate
make api      # backend on :8000
make web      # frontend on :5173
```
