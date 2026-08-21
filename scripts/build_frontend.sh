#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
STATIC_DIR="$ROOT_DIR/master/app/static"
NODE_VERSION="${PARS2RAY_NODE_VERSION:-22.14.0}"
NODE_DIR="$ROOT_DIR/.node"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) NODE_ARCH="x64" ;;
  aarch64|arm64) NODE_ARCH="arm64" ;;
  *) echo "Unsupported CPU architecture for bundled Node.js: $ARCH" >&2; exit 1 ;;
esac

command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }

if [[ ! -x "$NODE_DIR/bin/node" ]]; then
  archive="node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"
  url="https://nodejs.org/dist/v${NODE_VERSION}/${archive}"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl --fail --show-error --location --retry 3 --connect-timeout 10 --max-time 180 -o "$tmp/$archive" "$url"
  rm -rf "$NODE_DIR"
  mkdir -p "$NODE_DIR"
  tar -xJf "$tmp/$archive" --strip-components=1 -C "$NODE_DIR"
fi

export PATH="$NODE_DIR/bin:$PATH"
node --version
npm --version

cd "$FRONTEND_DIR"
npm ci --no-audit --no-fund
npm run build

[[ -f dist/index.html ]] || { echo "Frontend build did not produce dist/index.html" >&2; exit 1; }
rm -rf "$STATIC_DIR"
mkdir -p "$STATIC_DIR"
cp -a dist/. "$STATIC_DIR/"
[[ -f "$STATIC_DIR/index.html" ]] || { echo "Frontend was not installed into master/app/static" >&2; exit 1; }
