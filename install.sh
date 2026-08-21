#!/usr/bin/env bash
# Pars2Ray one-line bootstrap installer.
# Usage: curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/install.sh | sudo bash
set -Eeuo pipefail

REPO="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
REF="${PARS2RAY_REF:-main}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ "$(id -u)" != 0 ]]; then
  echo "[pars2ray] Please run as root (use: curl ... | sudo bash)." >&2
  exit 1
fi

command -v curl >/dev/null 2>&1 || {
  echo "[pars2ray] curl is required." >&2
  exit 1
}

echo "[pars2ray] Downloading installer..."
curl -fsSL --connect-timeout 10 --retry 3 "${REPO%.git}/raw/${REF}/deploy/install.sh" -o "$TMP/install.sh"
chmod 700 "$TMP/install.sh"

# Keep all existing installer environment variables intact.
bash "$TMP/install.sh" "$@"

INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
if [[ -f "$INSTALL_DIR/deploy/pars2ray" ]]; then
  install -m 0755 "$INSTALL_DIR/deploy/pars2ray" /usr/local/bin/pars2ray
  echo "[pars2ray] CLI installed: /usr/local/bin/pars2ray"
fi
