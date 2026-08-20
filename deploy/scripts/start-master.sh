#!/bin/sh
set -eu

# Fail fast if the database schema cannot be upgraded.
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
