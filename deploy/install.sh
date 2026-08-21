#!/usr/bin/env bash
set -Eeuo pipefail

# Pars2Ray Native Installer v3
# Design goals: one command, no Docker, safe re-runs, generated secrets,
# systemd services, simple CLI, useful failure diagnostics, and conservative
# network performance tuning for proxy nodes.

APP="pars2ray"
INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
DATA_DIR="${PARS2RAY_DATA_DIR:-${INSTALL_DIR}/data}"
ETC_DIR="/etc/pars2ray"
ENV_FILE="${ETC_DIR}/pars2ray.env"
CREDENTIALS_FILE="${ETC_DIR}/credentials"
REPOSITORY="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
REF="${PARS2RAY_REF:-main}"
PORT="${PARS2RAY_PANEL_PORT:-8000}"

log(){ printf '\033[1;36m[pars2ray]\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  !\033[0m %s\n' "$*" >&2; }
die(){ printf '\033[1;31m[pars2ray] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == 0 ]] || die "Run as root."
[[ -r /etc/os-release ]] || die "Cannot identify the operating system."
. /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *) die "Supported distributions: Ubuntu and Debian. Detected: ${ID:-unknown}" ;;
esac

command_exists(){ command -v "$1" >/dev/null 2>&1; }
random_hex(){ openssl rand -hex 32; }

read_env(){
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  awk -F= -v k="$key" '$1==k{sub(/^[^=]*=/," "); sub(/^ /,""); print; exit}' "$ENV_FILE"
}

set_env(){
  local key="$1" value="$2" tmp
  case "$value" in *$'\n'*|*$'\r'*) die "$key contains a newline";; esac
  install -d -m 0750 "$ETC_DIR"
  touch "$ENV_FILE"
  tmp="${ENV_FILE}.tmp.$$"
  awk -v k="$key" -v v="$value" 'BEGIN{done=0} $0 ~ "^" k "=" {if(!done){print k "=" v;done=1};next} {print} END{if(!done)print k "=" v}' "$ENV_FILE" > "$tmp"
  chmod 0600 "$tmp"
  mv -f "$tmp" "$ENV_FILE"
}

install_packages(){
  export DEBIAN_FRONTEND=noninteractive
  log "Installing required system packages..."
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git openssl python3 python3-venv python3-pip >/dev/null
  ok "System prerequisites ready"
}

fetch_source(){
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    log "Updating Pars2Ray source..."
    git -C "$INSTALL_DIR" fetch --depth 1 origin "$REF" >/dev/null 2>&1 || die "Could not fetch $REF from $REPOSITORY"
    git -C "$INSTALL_DIR" reset --hard "origin/$REF" >/dev/null
    git -C "$INSTALL_DIR" clean -fd >/dev/null
  elif [[ -e "$INSTALL_DIR" ]]; then
    die "$INSTALL_DIR exists and is not a Git checkout. Move it away or set PARS2RAY_INSTALL_DIR."
  else
    log "Downloading Pars2Ray..."
    install -d -m 0755 "$(dirname "$INSTALL_DIR")"
    git clone --depth 1 --branch "$REF" "$REPOSITORY" "$INSTALL_DIR" >/dev/null 2>&1 || die "Could not clone $REPOSITORY"
  fi
  ok "Source ready"
}

ensure_defaults(){
  install -d -m 0750 "$ETC_DIR" "$DATA_DIR"
  touch "$ENV_FILE"
  chmod 0600 "$ENV_FILE"

  local jwt master db host
  jwt="$(read_env JWT_SECRET)"; [[ -n "$jwt" ]] || jwt="$(random_hex)"
  master="$(read_env MASTER_SECRET)"; [[ -n "$master" ]] || master="$(random_hex)"
  db="$(read_env DATABASE_URL)"; [[ "$db" == sqlite:* ]] || db="sqlite:////${DATA_DIR#/}/pars2ray.db"
  host="$(hostname -I 2>/dev/null | awk '{print $1}')"; host="${host:-127.0.0.1}"

  set_env ENVIRONMENT production
  set_env DEBUG false
  set_env DATABASE_URL "$db"
  set_env REDIS_URL ""
  set_env JWT_SECRET "$jwt"
  set_env MASTER_SECRET "$master"
  set_env PARS2RAY_DATA_DIR "$DATA_DIR"
  set_env PANEL_HTTP_PORT "$PORT"
  set_env TRUSTED_HOSTS "localhost,127.0.0.1,$host"
}

prompt(){
  local label="$1" default="${2:-}" value
  if [[ -n "${PARS2RAY_NONINTERACTIVE:-}" || ! -t 0 ]]; then
    printf '%s' "$default"; return
  fi
  read -r -p "$label${default:+ [$default]}: " value || true
  printf '%s' "${value:-$default}"
}

prompt_password(){
  local value confirm
  if [[ -n "${PARS2RAY_ADMIN_PASSWORD:-}" ]]; then printf '%s' "$PARS2RAY_ADMIN_PASSWORD"; return; fi
  if [[ -n "${PARS2RAY_NONINTERACTIVE:-}" || ! -t 0 ]]; then printf '%s' "$(random_hex)$(random_hex)"; return; fi
  while :; do
    read -r -s -p "Panel password (12+ chars): " value || true; printf '\n'
    (( ${#value} >= 12 )) || { warn "Password must be at least 12 characters."; continue; }
    read -r -s -p "Confirm password: " confirm || true; printf '\n'
    [[ "$value" == "$confirm" ]] || { warn "Passwords do not match."; continue; }
    printf '%s' "$value"; return
  done
}

first_run(){
  local existing_user user email password host
  existing_user="$(read_env ADMIN_USER)"
  if [[ -n "$existing_user" ]]; then ok "Existing installation detected; keeping panel credentials and settings"; return; fi
  printf '\n\033[1;35m=== Pars2Ray setup ===\033[0m\n'
  printf 'A small first-run wizard will create the panel account.\n\n'
  user="${PARS2RAY_ADMIN_USER:-$(prompt 'Username' 'admin')}"
  [[ "$user" =~ ^[A-Za-z0-9_.-]{3,64}$ ]] || die "Username must be 3-64 characters: letters, numbers, _, ., -"
  email="${PARS2RAY_ADMIN_EMAIL:-$(prompt 'Email' 'admin@localhost')}"
  [[ "$email" == *@*.* || "$email" == *@localhost ]] || die "Invalid email address"
  password="$(prompt_password)"
  host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}') }"; host="${host// /}"; host="${host:-localhost}"
  set_env ADMIN_USER "$user"; set_env ADMIN_EMAIL "$email"; set_env ADMIN_PASSWORD "$password"; set_env PANEL_HTTP_PORT "$PORT"; set_env TRUSTED_HOSTS "localhost,127.0.0.1,$host"
  cat > "$CREDENTIALS_FILE" <<EOF
Pars2Ray installation
=====================
Panel: http://${host}:${PORT}
Username: ${user}
Password: ${password}

Keep this file private. It is readable only by root.
EOF
  chmod 0600 "$CREDENTIALS_FILE"
  ok "Panel account configured"
}

setup_python(){
  local venv="$INSTALL_DIR/.venv"
  if [[ ! -x "$venv/bin/python" ]]; then log "Creating isolated Python environment..."; python3 -m venv "$venv"; fi
  "$venv/bin/python" -m pip install --upgrade pip wheel >/dev/null 2>&1
  "$venv/bin/pip" install -q -r "$INSTALL_DIR/master/requirements.txt" || die "Python dependency installation failed"
  ok "Application dependencies ready"
  printf '%s' "$venv"
}

migrate(){
  local venv="$1"
  log "Applying database migrations..."
  export DATABASE_URL="$(read_env DATABASE_URL)"; export PYTHONPATH="$INSTALL_DIR/master"; cd "$INSTALL_DIR"
  "$venv/bin/alembic" upgrade head >/dev/null || die "Database migration failed"
  ok "Database ready"
}

write_services(){
  local venv="$1"
  cat > /etc/systemd/system/pars2ray-master.service <<EOF
[Unit]
Description=Pars2Ray Master Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONPATH=$INSTALL_DIR/master
ExecStart=$venv/bin/uvicorn app.main:app --app-dir $INSTALL_DIR/master --host 0.0.0.0 --port $PORT --proxy-headers --timeout-keep-alive 30 --limit-concurrency 1024
Restart=on-failure
RestartSec=3
LimitNOFILE=65535
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/pars2ray-worker.service <<EOF
[Unit]
Description=Pars2Ray Worker
After=network-online.target pars2ray-master.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONPATH=$INSTALL_DIR/master
ExecStart=$venv/bin/python -m app.worker
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF

  cat > /usr/local/bin/pars2ray <<'EOF'
#!/usr/bin/env bash
set -e
case "${1:-status}" in
  status) systemctl --no-pager --full status pars2ray-master pars2ray-worker ;;
  start) systemctl start pars2ray-master pars2ray-worker ;;
  stop) systemctl stop pars2ray-worker pars2ray-master ;;
  restart) systemctl restart pars2ray-master pars2ray-worker ;;
  logs) journalctl -u pars2ray-master -u pars2ray-worker -n 200 --no-pager ;;
  credentials) cat /etc/pars2ray/credentials ;;
  update) exec /opt/pars2ray/deploy/install.sh ;;
  uninstall) systemctl disable --now pars2ray-worker pars2ray-master 2>/dev/null || true; rm -f /etc/systemd/system/pars2ray-master.service /etc/systemd/system/pars2ray-worker.service /usr/local/bin/pars2ray; systemctl daemon-reload ;;
  *) echo 'Usage: pars2ray {status|start|stop|restart|logs|credentials|update|uninstall}'; exit 2 ;;
esac
EOF
  chmod 0755 /usr/local/bin/pars2ray
  systemctl daemon-reload
  systemctl enable pars2ray-master pars2ray-worker >/dev/null
  ok "systemd services installed"
}

# Enable BBR when the running kernel supports it. This is intentionally
# best-effort and never prevents installation. BBR generally improves
# throughput and latency under loss/congestion without hard-coding unsafe
# buffer sizes or changing firewall behavior.
tune_network(){
  [[ "${PARS2RAY_TUNE_NETWORK:-1}" == "1" ]] || { warn "Network tuning disabled by PARS2RAY_TUNE_NETWORK=0"; return; }
  command_exists sysctl || return
  local available current
  available="$(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null || true)"
  if grep -qw bbr <<<"$available"; then
    current="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"
    if [[ "$current" != "bbr" ]]; then
      sysctl -w net.ipv4.tcp_congestion_control=bbr >/dev/null 2>&1 || true
    fi
    cat > /etc/sysctl.d/99-pars2ray-network.conf <<'EOF'
# Pars2Ray: use BBR when supported by the kernel.
net.ipv4.tcp_congestion_control=bbr
EOF
    sysctl --system >/dev/null 2>&1 || true
    ok "TCP BBR enabled for supported kernels"
  else
    warn "Kernel does not expose BBR; keeping the system congestion-control defaults"
  fi
}

health_check(){
  local attempt url="http://127.0.0.1:${PORT}/health"
  log "Starting Pars2Ray..."
  systemctl restart pars2ray-master
  for attempt in $(seq 1 45); do
    if curl -fsS --connect-timeout 1 --max-time 2 "$url" >/dev/null 2>&1; then
      ok "Panel is responding"; systemctl restart pars2ray-worker; ok "Worker started"; return 0
    fi
    sleep 1
  done
  journalctl -u pars2ray-master -n 100 --no-pager >&2 || true
  die "Panel did not become ready. Run: pars2ray logs"
}

print_result(){
  local host user
  host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}') }"; host="${host// /}"; host="${host:-localhost}"
  user="$(read_env ADMIN_USER)"
  printf '\n\033[1;32m==============================================\033[0m\n'
  printf '\033[1;32m Pars2Ray is installed and running\033[0m\n'
  printf '\033[1;32m==============================================\033[0m\n'
  printf ' Panel:       http://%s:%s\n' "$host" "$PORT"
  printf ' Username:    %s\n' "$user"
  printf ' Credentials: %s\n' "$CREDENTIALS_FILE"
  printf ' CLI:         pars2ray status\n'
  printf ' Logs:        pars2ray logs\n\n'
}

main(){
  install_packages
  fetch_source
  ensure_defaults
  first_run
  local venv; venv="$(setup_python)"
  migrate "$venv"
  write_services "$venv"
  tune_network
  health_check
  print_result
}

main "$@"
