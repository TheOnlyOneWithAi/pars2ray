#!/bin/sh
set -eu

# Keep worker startup consistent with the API container schema.
alembic upgrade head

exec python -m app.worker
