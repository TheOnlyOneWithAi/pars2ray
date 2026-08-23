#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
ENV_FILE="/etc/pars2ray/pars2ray.env"
LOCK_FILE="/run/lock/pars2ray-auto-update.lock"
LOG_TAG="pars2ray-auto-update"
REPOSITORY="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
REF="${PARS2RAY_REF:-main}"

log(){ printf '[%s] %s\n' "$LOG_TAG" "$*"; }
warn(){ printf '[%s] WARNING: %s\n' "$LOG_TAG" "$*" >&2; }
die(){ printf '[%s] ERROR: %s\n' "$LOG_TAG" "$*" >&2; exit 1; }

[[ "$(id -u)" == 0 ]] || die "must run as root"
[[ -d "$INSTALL_DIR/.git" ]] || die "installation is not a git checkout"
[[ -r "$ENV_FILE" ]] || die "environment file is missing"
command -v git >/dev/null || die "git is required"
command -v systemctl >/dev/null || die "systemctl is required"
command -v flock >/dev/null || die "flock is required"

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

[[ "${PARS2RAY_AUTO_UPDATE_ENABLED:-1}" == "1" ]] || { log "automatic updates disabled"; exit 0; }

exec 9>"$LOCK_FILE"
flock -n 9 || { log "another update is already running"; exit 0; }

cd "$INSTALL_DIR"
CURRENT="$(git rev-parse HEAD)"
REMOTE="$(git ls-remote "$REPOSITORY" "refs/heads/$REF" | awk '{print $1}')"
[[ "$REMOTE" =~ ^[0-9a-f]{40}$ ]] || die "could not resolve remote revision"
[[ "$REMOTE" != "$CURRENT" ]] || { log "already up to date at ${CURRENT:0:12}"; exit 0; }

log "new revision detected: ${CURRENT:0:12} -> ${REMOTE:0:12}"

# Never destroy local modifications automatically. Panel data and /etc settings
# remain outside the source checkout and are therefore preserved.
[[ -z "$(git status --porcelain)" ]] || die "working tree is dirty; refusing automatic update"

BACKUP_REF="$CURRENT"
BACKUP_BRANCH="pars2ray-auto-backup-$(date +%Y%m%d%H%M%S)"
git branch "$BACKUP_BRANCH" "$CURRENT" >/dev/null
cleanup(){ git branch -D "$BACKUP_BRANCH" >/dev/null 2>&1 || true; }
trap cleanup EXIT

git fetch --depth 2 origin "$REF"
git checkout --detach "$REMOTE" >/dev/null

rollback(){
  warn "update failed; rolling back to ${BACKUP_REF:0:12}"
  git reset --hard "$BACKUP_REF" >/dev/null 2>&1 || true
  "$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/master/requirements.txt" >/dev/null 2>&1 || true
  export PYTHONPATH="$INSTALL_DIR/master"
  "$INSTALL_DIR/.venv/bin/alembic" upgrade head >/dev/null 2>&1 || true
  systemctl daemon-reload || true
  systemctl restart pars2ray-master.service pars2ray-worker.service || true
}
trap 'rc=$?; if ((rc != 0)); then rollback; fi; exit $rc' EXIT

log "installing application dependencies"
"$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/master/requirements.txt"
export PYTHONPATH="$INSTALL_DIR/master"

log "validating database migrations"
"$INSTALL_DIR/.venv/bin/alembic" upgrade head

log "reloading services"
systemctl daemon-reload
systemctl restart pars2ray-master.service pars2ray-worker.service

PORT="${PANEL_HTTP_PORT:-8000}"
for _ in $(seq 1 45); do
  if curl -fsS --connect-timeout 1 --max-time 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    log "health check passed"
    trap - EXIT
    git branch -D "$BACKUP_BRANCH" >/dev/null 2>&1 || true
    log "update completed successfully at ${REMOTE:0:12}"
    exit 0
  fi
  sleep 1
done

die "health check failed after update"
