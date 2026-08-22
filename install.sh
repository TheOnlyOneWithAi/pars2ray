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
export APT_CONFIG="$TMP/apt-installer.conf"

# Never advertise the loopback-only Uvicorn port to the user.
sed -i 's#Panel: http://${host}:${PORT}#Panel: http://${host}#' "$TMP/install.sh"
sed -i 's# Panel:       http://%s:%s# Panel:       http://%s#' "$TMP/install.sh"

bash "$TMP/install.sh" "$@"

INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
DATA_DIR="${PARS2RAY_DATA_DIR:-${INSTALL_DIR}/data}"
ETC_DIR="/etc/pars2ray"
ENV_FILE="${ETC_DIR}/pars2ray.env"
PORT="${PARS2RAY_PANEL_PORT:-8000}"

read_env(){ local key="$1"; [[ -f "$ENV_FILE" ]] || return 0; awk -F= -v k="$key" '$1==k{sub(/^[^=]*=/,"" ); print; exit}' "$ENV_FILE"; }
log(){ printf '\033[1;36m[pars2ray]\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[pars2ray] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

configured_port="$(read_env PANEL_HTTP_PORT || true)"
[[ "$configured_port" =~ ^[0-9]+$ ]] && PORT="$configured_port"
(( PORT >= 1 && PORT <= 65535 )) || die "Invalid Pars2Ray panel port: $PORT"

install -d -m 0755 /etc/nginx/conf.d /etc/nginx/sites-enabled /var/www/letsencrypt "$DATA_DIR"
rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/pars2ray.conf
cat > "$DATA_DIR/panel-nginx.conf" <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    server_tokens off;
    client_max_body_size 10m;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    location ~ /\\. {
        deny all;
    }
}
EOF
ln -sfn "$DATA_DIR/panel-nginx.conf" /etc/nginx/conf.d/pars2ray.conf
nginx -t >/dev/null || die "Nginx configuration validation failed"
systemctl reload nginx || systemctl restart nginx || die "Could not reload/restart nginx"

# HTTP is the public entrypoint. If UFW is installed and active, allow the
# public listener; never expose the internal Uvicorn port.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
  ufw allow 80/tcp >/dev/null || die "Could not allow HTTP through UFW"
  ufw delete allow 8000/tcp >/dev/null 2>&1 || true
fi

systemctl daemon-reload
systemctl enable pars2ray-master pars2ray-worker >/dev/null 2>&1 || die "Could not enable Pars2Ray services"
systemctl restart pars2ray-master
systemctl restart pars2ray-worker

ready=0
for _ in $(seq 1 30); do
  if curl -fsS --connect-timeout 2 --max-time 3 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
(( ready == 1 )) || die "Pars2Ray backend did not become healthy on 127.0.0.1:${PORT}"

public_ready=0
for _ in $(seq 1 15); do
  if curl -fsS --connect-timeout 2 --max-time 3 -H 'Host: localhost' http://127.0.0.1/health >/dev/null 2>&1; then public_ready=1; break; fi
  sleep 1
done
(( public_ready == 1 )) || { nginx -T 2>&1 | tail -n 160 >&2 || true; die "Nginx reverse proxy health check failed on http://127.0.0.1/health"; }

host="${PARS2RAY_PUBLIC_HOST:-}"
[[ -n "$host" ]] || host="$(hostname -I 2>/dev/null | awk '{print $1}')"
host="${host:-localhost}"
user="$(read_env ADMIN_USER || true)"
password="$(read_env ADMIN_PASSWORD || true)"
if [[ -n "$user" && -n "$password" ]]; then
  umask 077
  cat > /etc/pars2ray/credentials <<EOF
Pars2Ray installation
=====================
Panel: http://${host}
Username: ${user}
Password: ${password}

Keep this file private. It is readable only by root.
EOF
  chmod 0600 /etc/pars2ray/credentials
fi

ok "Backend health check passed"
ok "Nginx reverse-proxy health check passed"
ok "Panel: http://${host}"
