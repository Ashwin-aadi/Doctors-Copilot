# Deployment

The whole stack — Postgres, Redis, Neo4j, the API and the web app behind nginx —
comes up with one command. Everything below assumes a machine with Docker and
nothing else installed.

## Quickstart

```bash
git clone <repo> && cd doctor-copilot
cp .env.example .env          # then edit, see "Before the first deploy"
make prod-up                  # build and start everything
./scripts/deploy_check.sh     # assert it is actually serving
make prod-seed                # demo data: clinics, doctors, patients, visits
```

The app is then on <http://localhost> and the API on <http://localhost:8000>.

## Before the first deploy

Two values in `.env` must change. Nothing else has to.

| Variable | Why |
|---|---|
| `SECRET_KEY` | Signs every JWT and password-reset token. Anyone who knows it can mint a token for any user, including a doctor. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GROQ_API_KEY` | The hosted model tier. Free key from <https://console.groq.com>. Without it the stack still runs — the gateway falls back to a local model, then to extractive answers — but briefs will not be generated. |

Check `CAPTCHA_ENABLED=true` while you are in there. It defaults to on in code
and is only worth turning off for load testing.

`.env` is gitignored and never enters an image; the compose file reads it at
runtime.

## Ports

Defaults are 80 for the web app and 8000 for the API. Override either when
something already holds them:

```bash
WEB_HOST_PORT=8090 API_HOST_PORT=8010 make prod-up
```

`deploy_check.sh` reads the same two variables, so pass them there too.

## What the stack does on start

1. Postgres, Redis and Neo4j come up and must report healthy before the API is
   started at all.
2. The API container applies `alembic upgrade head` and only then execs
   gunicorn — a fresh volume gets its schema without anyone remembering to run
   a migration.
3. nginx waits for the API to pass its health check, then serves the built
   frontend and proxies `/api`, `/ws` and `/health` to it.

Because the browser only ever talks to nginx, `VITE_API_BASE` is empty in the
image: requests go to `/api` on the page's own origin. Nothing has to know the
API's hostname.

## Volumes

| Volume | Holds | Losing it means |
|---|---|---|
| `pgdata` | Postgres | Everything clinical. Back this up. |
| `neo4jdata` | The patient graph | Rebuildable — it is a projection of Postgres, `sync_patient` rewrites it. |
| `storage` | Uploaded reports | Uploaded PDFs are gone. |
| `./infra/chroma` (bind) | The retrieval index | Re-ingest; the brief loses its citations until you do. |
| `../ml/.cache` (bind) | Model weights, ~1 GB | Re-downloaded on next start. |

The two bind mounts are deliberate: both are large and slow to rebuild, so a
rebuilt image reuses whatever the host already has, and degrades to
downloading or ingesting when the host has nothing.

## Everyday commands

```bash
make prod-up        # build and start (also the way to redeploy a change)
make prod-down      # stop
make prod-logs      # tail the API
make prod-seed      # demo data
make deploy-check   # is it actually serving?
```

## Verifying a deploy

`deploy_check.sh` exists because a container reports healthy long before the app
is usable — a database accepts connections with no tables in it, and nginx will
happily serve an index page that fails on its first API call. It checks the
things a demo actually breaks on:

- every service running
- `/health` reports no dependency `down`
- the schema is migrated (the `visits` table exists)
- OpenAPI is served and contains the contracted paths
- an API call routed **through nginx** returns an error envelope rather than the
  SPA fallback, which proves the proxy reaches the API rather than swallowing
  the path

It prints `DEPLOY OK` and exits 0, or names what failed and exits 1.

## Troubleshooting

**`port is already allocated`** — something holds 80 or 8000. Use
`WEB_HOST_PORT` / `API_HOST_PORT` above.

**The API restarts in a loop.** `make prod-logs`. Almost always the migration:
it runs before the server, so a bad revision stops the container rather than
serving a half-migrated schema.

**Briefs come back without citations.** The retrieval index is empty. Ingest it,
or copy an `infra/chroma` from a machine that has one.

**Briefs are extractive and say the model was unavailable.** `GROQ_API_KEY` is
missing or its free-tier quota is spent. The gateway falls back rather than
failing the request, which is why the app keeps working.

**Health shows `neo4j: down`.** The graph is optional by design — every read
degrades to an empty-but-valid shape. The app works; the brief loses history.

## Notes for a public deployment

This is built for a hackathon demo and a clinic pilot, not for the open
internet. Before exposing it:

- Put TLS in front of nginx; the config here listens on plain 80.
- Change the Postgres and Neo4j passwords from their compose defaults.
- Session tokens live in `localStorage`, not `httpOnly` cookies — fine behind a
  trusted network, worth changing before public exposure.
- `APP_ENV=prod` (set for you in `infra/prod.env`) enables the upload screening
  that is advisory in dev.
