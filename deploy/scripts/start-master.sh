#!/bin/sh
set -eu

# Wait for PostgreSQL to accept connections before running migrations.
# The compose healthcheck can become healthy while the server is still
# completing startup/recovery, so the application performs its own retry.
max_attempts="${DB_STARTUP_RETRIES:-30}"
delay="${DB_STARTUP_DELAY:-2}"
attempt=1

while ! python - <<'PY'
import os
from sqlalchemy import create_engine

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL is not configured")

engine = create_engine(url, pool_pre_ping=True)
try:
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")
finally:
    engine.dispose()
PY
do
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "ERROR: PostgreSQL was not ready after $max_attempts attempts." >&2
    exit 1
  fi
  echo "Waiting for PostgreSQL (attempt $attempt/$max_attempts)..."
  sleep "$delay"
  attempt=$((attempt + 1))
done

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
