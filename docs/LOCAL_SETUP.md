# Running this locally

Written for a coding agent. Point your agent at this file and it should get the
stack up without guessing. Humans can follow it too — it is ordinary
instructions, just unusually explicit about the traps.

Almost every "it doesn't work on my machine" report on this project is one of
five things, and none of them are obvious from the code:

1. Two `.env` files are needed, not one, and neither is in git.
2. `python-magic` needs an extra package on Windows that is not in
   `requirements.txt`.
3. The API must be started with `run.py`, never bare `uvicorn`.
4. The retrieval index is 95 MB and gitignored, so a fresh clone has no
   citations.
5. The model weights are ~1.1 GB and download on first run.

Read the whole file before starting. It is short.

---

## 0. What you need installed

- Python 3.11 or 3.12
- Node 20+
- Docker Desktop, running

---

## 1. Databases

```bash
make up      # postgres, redis, neo4j
```

**If port 5432 is already taken** (another project's Postgres — common), pick a
different published port and make the URL agree. Both, or nothing works:

```bash
# in .env, after you create it in step 2
POSTGRES_PORT=5544
DATABASE_URL=postgresql+psycopg://copilot:copilot@localhost:5544/copilot
```

Only the *published* port changes. Inside the container Postgres is always on
5432, so `POSTGRES_PORT` and the port in `DATABASE_URL` must match each other
and nothing else.

Check all three are healthy before continuing:

```bash
docker compose -f infra/docker-compose.yml ps
```

---

## 2. The two `.env` files

Both are gitignored. Pulling `main` gives you neither. This is the single most
common cause of a broken setup.

### 2a. Repo root `.env`

```bash
cp .env.example .env
```

Then set two values:

**`SECRET_KEY`** — signs every login token. Generate your own:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Any random value works for local development; it does not need to match
anyone else's. It must stay *stable* on your machine, though — changing it
invalidates every token you already hold, so you get logged out and any tab you
had open starts failing with 401. If that happens, log in again.

Do not ship the placeholder from `.env.example`. It is published in this repo,
which makes it equivalent to no authentication at all.

**`GROQ_API_KEY`** — optional. Free key at <https://console.groq.com>. Without
it everything still runs: the model gateway falls back to a local Ollama
instance, then to extractive text. You will see briefs that say the model was
unavailable. That is the fallback working, not a bug.

### 2b. `frontend/.env`

**This file does not exist after a clone and you have to create it.** If you
skip it, the web app calls `http://localhost:8000` no matter what the root
`.env` says — Vite only reads `.env` from inside `frontend/`, and the root file
is invisible to it.

```bash
# frontend/.env  -- must match the port you start the API on in step 5
VITE_API_BASE=http://localhost:8000
```

Symptom when this is wrong: the page loads fine, looks correct, and every
request fails. Login spins or 404s. Nothing in the backend log, because the
request never reached the backend.

---

## 3. Dependencies

```bash
make install     # backend requirements + frontend npm ci
```

### On Windows, one extra package

`python-magic` binds to a native library that Windows does not have.
`requirements.txt` does not list the Windows shim, so install it yourself:

```bash
pip install python-magic-bin==0.4.14
```

Skip this and the **entire API fails to start** — not just uploads. The import
runs through the router at module scope, so you get
`ImportError: failed to find libmagic` and no server at all.

On macOS: `brew install libmagic`. On Linux: `sudo apt install libmagic1`.

### First run downloads ~1.1 GB of models

Sentence-transformers and the cross-encoder are fetched on first use into
`ml/.cache` (`HF_HOME` points there). Expect several minutes on the first
request that touches retrieval, and nothing at all on later ones.

If the download dies partway, delete `ml/.cache` and let it start over —
a half-written cache fails in confusing ways.

---

## 4. Schema and data

```bash
cd backend && alembic upgrade head && cd ..
python scripts/seed.py            # clinics, doctors, patients, one demo visit
python scripts/seed_doctors.py    # 54 doctors across 11 facilities, 9 states
```

Both seeds are idempotent — safe to re-run.

You will see `error reading bcrypt version` with a traceback. **Ignore it.** It
is a cosmetic mismatch between `passlib` and `bcrypt`; the line after it says
`seed OK`.

---

## 5. Run it

Two terminals.

```bash
# terminal 1 -- API
cd backend
python run.py --reload --port 8000
```

**Never `uvicorn app.main:app` directly.** On Windows, uvicorn builds its event
loop before importing the app, so the app's own event-loop policy switch lands
too late and you end up on a ProactorEventLoop. Async psycopg refuses to run
there, so *every database request returns 500* while the server looks perfectly
healthy. `run.py` sets the policy first. This is the second most common broken
setup after the missing `frontend/.env`.

If port 8000 is taken, use another — and change `frontend/.env` to match:

```bash
python run.py --reload --port 8001     # then VITE_API_BASE=http://localhost:8001
```

```bash
# terminal 2 -- web app
cd frontend
npm run dev
```

The dev server is pinned to **5174** with `strictPort`, deliberately. If the
port is busy it fails loudly rather than silently moving to another one and
leaving you staring at a stale tab.

Open <http://localhost:5174>.

---

## 6. Log in

Seeded accounts, password **`demo-password-123`**:

| Role | Email |
|---|---|
| Doctor | `doctor1@doctorcopilot.dev` … `doctor6@doctorcopilot.dev` |
| Patient | see `docs/DEMO_ACCOUNTS.md` |

A captcha appears on login and registration. It is a proof-of-work puzzle the
browser solves by itself in about a second — no clicking, no third party. If you
are scripting against the API you must solve it yourself and send the result as
an `X-Captcha-Token` header; see `docs/CAPTCHA.md`. To turn it off while
developing, set `CAPTCHA_ENABLED=false` in the root `.env`.

---

## 7. The retrieval index

This is the one thing a clone genuinely cannot give you.

The clinical corpus lives in `backend/infra/chroma` — about 95 MB, gitignored.
Without it the app runs, triage works, and **the clinical brief comes back with
no citations**, which looks like a bug and is not one.

Two ways to get it:

- **Copy `backend/infra/chroma/` from a teammate who has it.** Far faster.
- **Ingest it yourself:** `python -m app.rag.ingest_clinical` from `backend/`.
  Takes a long time and needs network access.

Confirm it worked:

```bash
cd backend && python -c "from app.rag.store import VectorStore; v=VectorStore(); print('clinical:', v.count('clinical'))"
```

You want a few thousand. Zero means the index is missing or in the wrong place.

**Watch the path.** `CHROMA_PATH` in `.env` is relative (`./infra/chroma`) and
the backend runs with `cwd=backend`, so it resolves to `backend/infra/chroma` —
*not* the `infra/chroma` at the repo root. Those are two different directories
and the root one may hold a stale copy. Put the index in the `backend/` one.

---

## The alternative: run everything in Docker

If the above is fighting you, skip all of it. This path has none of the Windows
quirks because everything runs in Linux containers:

```bash
cp .env.example .env       # still set SECRET_KEY and GROQ_API_KEY
make prod-up
./scripts/deploy_check.sh  # tells you what is actually broken, if anything
make prod-seed
```

Web app on <http://localhost>, API on :8000. If those ports are taken:

```bash
WEB_HOST_PORT=8090 API_HOST_PORT=8010 make prod-up
```

Pass the same variables to `deploy_check.sh`. Migrations run automatically
inside the container. First build pulls several GB and takes a while.

See `docs/DEPLOYMENT.md` for the full story.

---

## Symptom → cause

| What you see | What it is |
|---|---|
| Page loads, every request fails, backend log silent | `frontend/.env` missing or its port disagrees with the API's |
| `ImportError: failed to find libmagic`, API won't start | `pip install python-magic-bin==0.4.14` (Windows) |
| Every DB request 500s, server looks fine | Started with bare `uvicorn`. Use `python run.py` |
| `connection refused` on Postgres | `make up` not run, or `POSTGRES_PORT` disagrees with `DATABASE_URL` |
| Brief has no citations | Retrieval index missing — see section 7 |
| Brief says the model was unavailable | No `GROQ_API_KEY`, or free quota spent. Fallback working as designed |
| Logged out constantly, 401 everywhere | `SECRET_KEY` changed since you logged in. Log in again |
| `error reading bcrypt version` | Cosmetic. Ignore |
| Vite won't start on 5174 | Port busy. Free it — the pin is deliberate |
| `health` says `neo4j: down` | Graph is optional; the app works, the brief loses patient history |

## Checking your setup end to end

```bash
curl -s http://localhost:8000/health
```

Every dependency should read `ok`:

```json
{"status":"ok","db":"ok","redis":"ok","neo4j":"ok","chroma":"ok","llm":"ok"}
```

`chroma: ok` only means the store is reachable — it does **not** mean the corpus
is loaded. Use the count command in section 7 for that.

Then run the suites:

```bash
cd backend && pytest -q          # expect ~607 passed
cd frontend && npm run test -- --run
```
