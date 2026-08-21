#!/bin/sh
set -eu

# The master service owns Alembic migrations. Starting migrations from both
# master and worker concurrently can race on a fresh database. The worker is
# started only after the master health check passes (see docker-compose.yml).
max_attempts="${DB_STARTUP_RETRIES:-30}"
delay="${DB_STARTUP_DELAY:-2}"
attempt=1

while :; do
  if python - <<'PY'
import os
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL is not configured")

engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1 FROM alembic_version LIMIT 1"))
finally:
    engine.dispose()
PY
  then
    break
  fi

  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "ERROR: database schema was not ready after $max_attempts attempts." >&2
    exit 1
  fi
  echo "Waiting for migrated database (attempt $attempt/$max_attempts)..." >&2
  sleep "$delay"
  attempt=$((attempt + 1))
done

exec python -m app.worker
