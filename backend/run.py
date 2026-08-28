"""Dev entrypoint.

Uvicorn builds its event loop before it imports `app.main`, so the
`WindowsSelectorEventLoopPolicy` switch inside that module lands too late and
the server ends up on a ProactorEventLoop -- which async psycopg refuses to
run on, failing every database-backed request with a 500. Setting the policy
here, before uvicorn is touched at all, keeps the selector loop in place.

Usage: python run.py [--port 8001]
"""

import argparse
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
