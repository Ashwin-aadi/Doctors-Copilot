#!/usr/bin/env sh
# Bring the schema up to date before serving. Compose already waits for postgres
# to report healthy, but healthy only means it accepts connections -- the
# database behind a fresh volume still has no tables, and every request would
# 500 until someone remembered to run the migration by hand.
set -eu

echo "applying migrations"
alembic upgrade head

exec "$@"
