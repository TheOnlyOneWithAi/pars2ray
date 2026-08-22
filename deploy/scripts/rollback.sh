#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
TARGET="${1:-}"
[[ "$(id -u)" == 0 ]] || { echo "rollback must run as root" >&2; exit 2; }
[[ -d "$INSTALL_DIR/.git" ]] || { echo "Pars2Ray installation is not a git checkout" >&2; exit 3; }
[[ -n "$TARGET" ]] || TARGET="HEAD~1"
if ! git -C "$INSTALL_DIR" rev-parse --verify "$TARGET^{commit}" >/dev/null 2>&1; then echo "unknown rollback target: $TARGET" >&2; exit 4; fi
CURRENT="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
if [[ "$TARGET" == "$CURRENT" ]]; then echo "already at $TARGET"; exit 0; fi
BACKUP_DIR="${PARS2RAY_ROLLBACK_DIR:-$INSTALL_DIR/data/rollback}"
mkdir -p "$BACKUP_DIR"
printf '%s\n' "$CURRENT" > "$BACKUP_DIR/previous-$(date -u +%Y%m%dT%H%M%SZ).commit"
git -C "$INSTALL_DIR" diff --quiet && git -C "$INSTALL_DIR" diff --cached --quiet || { echo "working tree is dirty; refusing rollback" >&2; exit 5; }
git -C "$INSTALL_DIR" reset --hard "$TARGET"
if command -v systemctl >/dev/null 2>&1; then systemctl daemon-reload; systemctl restart pars2ray-master pars2ray-worker; fi
echo "rolled back to $(git -C "$INSTALL_DIR" rev-parse HEAD)"
