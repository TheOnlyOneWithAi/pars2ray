#!/usr/bin/env bash
# Pars2Ray one-line native installer bootstrap.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/install.sh | sudo bash
set -Eeuo pipefail

REPO="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
REF="${PARS2RAY_REF:-main}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ "$(id -u)" != 0 ]]; then
  echo "[pars2ray] Run as root (for example: sudo bash)." >&2
  exit 1
fi

command -v curl >/dev/null 2>&1 || {
  echo "[pars2ray] curl is required." >&2
  exit 1
}

echo "[pars2ray] Downloading native installer..."
curl -fsSL --connect-timeout 10 --retry 3 "${REPO%.git}/raw/${REF}/deploy/install.sh" -o "$TMP/install.sh"
curl -fsSL --connect-timeout 10 --retry 3 "${REPO%.git}/raw/${REF}/deploy/apt-installer.conf" -o "$TMP/apt-installer.conf"
chmod 700 "$TMP/install.sh"
chmod 600 "$TMP/apt-installer.conf"

# Apply transport-level APT safeguards before the native installer invokes apt-get.
# In particular, force IPv4 because some VPS networks have broken/slow IPv6 paths.
export APT_CONFIG="$TMP/apt-installer.conf"

# The native installer owns the complete installation lifecycle.
# No Docker, Compose, PostgreSQL or Redis setup is performed here.
exec bash "$TMP/install.sh" "$@"
