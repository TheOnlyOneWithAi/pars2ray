#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
DATA_DIR="${PARS2RAY_DATA_DIR:-$INSTALL_DIR/data}"
ETC_DIR="${PARS2RAY_ETC_DIR:-/etc/pars2ray}"
OUT="${1:-${PARS2RAY_BACKUP_DIR:-$DATA_DIR/backups}}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
DB="${DATABASE_URL:-}"
if [[ -z "$DB" && -f "$ETC_DIR/pars2ray.env" ]]; then
  DB="$(awk -F= '$1=="DATABASE_URL"{sub(/^[^=]*=/,"");print;exit}' "$ETC_DIR/pars2ray.env")"
fi
[[ "$DB" == sqlite:* ]] || { echo "native backup supports SQLite DATABASE_URL only" >&2; exit 2; }
DB_PATH="${DB#sqlite:////}"
[[ -f "$DB_PATH" ]] || { echo "database not found: $DB_PATH" >&2; exit 3; }
cp -a "$DB_PATH" "$OUT/pars2ray-$STAMP.db"
if [[ -f "$ETC_DIR/pars2ray.env" ]]; then cp -a "$ETC_DIR/pars2ray.env" "$OUT/pars2ray-$STAMP.env"; fi
printf '%s\n' "$OUT/pars2ray-$STAMP.db"
