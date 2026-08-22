#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
DATA_DIR="${PARS2RAY_DATA_DIR:-$INSTALL_DIR/data}"
ETC_DIR="${PARS2RAY_ETC_DIR:-/etc/pars2ray}"
BACKUP="${1:-}"
[[ -n "$BACKUP" && -f "$BACKUP" ]] || { echo "usage: native-restore.sh /path/to/backup.db" >&2; exit 2; }
[[ "$(id -u)" == 0 ]] || { echo "restore must run as root" >&2; exit 3; }
DB="${DATABASE_URL:-}"
if [[ -z "$DB" && -f "$ETC_DIR/pars2ray.env" ]]; then DB="$(awk -F= '$1=="DATABASE_URL"{sub(/^[^=]*=/,"");print;exit}' "$ETC_DIR/pars2ray.env")"; fi
[[ "$DB" == sqlite:* ]] || { echo "native restore supports SQLite DATABASE_URL only" >&2; exit 4; }
DB_PATH="${DB#sqlite:////}"
install -d -m 0750 "$(dirname "$DB_PATH")" "$DATA_DIR"
if [[ -f "$DB_PATH" ]]; then cp -a "$DB_PATH" "$DB_PATH.pre-restore.$(date -u +%Y%m%dT%H%M%SZ)"; fi
install -m 0600 "$BACKUP" "$DB_PATH"
chown --reference="$(dirname "$DB_PATH")" "$DB_PATH" 2>/dev/null || true
printf '%s\n' "restored $DB_PATH"
