#!/bin/sh
set -eu

max_attempts="${DB_STARTUP_RETRIES:-30}"
delay="${DB_STARTUP_DELAY:-2}"
attempt=1

while :; do
  if python - <<'PY'
import os
from sqlalchemy import create_engine

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL is not configured")

engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
try:
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")
finally:
    engine.dispose()
PY
  then
    break
  fi

  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "ERROR: PostgreSQL was not ready after $max_attempts attempts." >&2
    exit 1
  fi
  echo "Waiting for PostgreSQL (attempt $attempt/$max_attempts)..." >&2
  sleep "$delay"
  attempt=$((attempt + 1))
done

echo "PostgreSQL is ready; applying migrations..." >&2
if ! alembic upgrade head; then
  echo "ERROR: Alembic migration failed." >&2
  exit 1
fi

echo "Migrations complete; starting Pars2Ray master on 0.0.0.0:8000..." >&2
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --timeout-keep-alive 15
