#!/bin/sh
set -eu
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${BACKUP_DIR:-./backups}
mkdir -p "$OUT"
docker compose --env-file .env -f deploy/docker-compose.yml exec -T db pg_dump -U pars2ray -d pars2ray | gzip > "$OUT/pars2ray-postgres-$STAMP.sql.gz"
docker compose --env-file .env -f deploy/docker-compose.yml exec -T redis redis-cli --rdb /tmp/dump.rdb >/dev/null 2>&1 || true
docker compose --env-file .env -f deploy/docker-compose.yml cp redis:/data/dump.rdb "$OUT/pars2ray-redis-$STAMP.rdb" 2>/dev/null || true
echo "backup written to $OUT"
