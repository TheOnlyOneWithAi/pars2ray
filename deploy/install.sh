#!/usr/bin/env bash
set -Eeuo pipefail

PARS2RAY_REPOSITORY="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
PARS2RAY_REF="${PARS2RAY_REF:-main}"
PARS2RAY_INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
PARS2RAY_DATA_DIR="${PARS2RAY_DATA_DIR:-${PARS2RAY_INSTALL_DIR}/data}"
PARS2RAY_ENV_FILE="${PARS2RAY_INSTALL_DIR}/.env"
PARS2RAY_SERVICE_USER="${PARS2RAY_SERVICE_USER:-pars2ray}"
PARS2RAY_FIRST_INSTALL=0

log(){ printf '[pars2ray] %s\n' "$*"; }
die(){ printf '[pars2ray] ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || die "Run as root"
[[ -r /etc/os-release ]] || die "Ubuntu/Debian required"; . /etc/os-release
case "${ID:-}" in ubuntu|debian) ;; *) die "Unsupported distribution: ${ID:-unknown}" ;; esac

install_prerequisites(){
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git openssl python3 python3-venv python3-pip
}

checkout_project(){
  if [[ -d "$PARS2RAY_INSTALL_DIR/.git" ]]; then
    log "Updating existing Pars2Ray checkout"
    git -C "$PARS2RAY_INSTALL_DIR" fetch --depth 1 origin "$PARS2RAY_REF"
    git -C "$PARS2RAY_INSTALL_DIR" checkout --force "$PARS2RAY_REF"
    git -C "$PARS2RAY_INSTALL_DIR" reset --hard "origin/$PARS2RAY_REF"
  elif [[ -e "$PARS2RAY_INSTALL_DIR" ]]; then
    die "$PARS2RAY_INSTALL_DIR exists but is not a Git checkout"
  else
    PARS2RAY_FIRST_INSTALL=1
    install -d -m 0755 "$(dirname "$PARS2RAY_INSTALL_DIR")"
    git clone --depth 1 --branch "$PARS2RAY_REF" "$PARS2RAY_REPOSITORY" "$PARS2RAY_INSTALL_DIR"
  fi
}

read_env_value(){
  local key="$1"
  [[ -f "$PARS2RAY_ENV_FILE" ]] || return 0
  awk -F= -v wanted="$key" '$1==wanted{sub(/^[^=]*=/,"");print;exit}' "$PARS2RAY_ENV_FILE"
}

set_env_value(){
  local key="$1" value="$2" tmp="${PARS2RAY_ENV_FILE}.tmp.$$"
  case "$value" in *$'\n'*|*$'\r'*) die "$key cannot contain a newline";; esac
  awk -v w="$key" -v r="$value" 'BEGIN{f=0}$0~"^"w"="{if(!f){print w"="r;f=1};next}{print}END{if(!f)print w"="r}' "$PARS2RAY_ENV_FILE" > "$tmp"
  chmod 600 "$tmp"; mv -f "$tmp" "$PARS2RAY_ENV_FILE"
}

random_hex(){ openssl rand -hex 32; }
prompt_value(){ local p="$1" d="${2:-}" v; read -r -p "$p${d:+ [$d]}: " v || true; printf '%s' "${v:-$d}"; }
prompt_secret(){
  local p="$1" v c
  while true; do
    read -r -s -p "$p: " v || true; printf '\n'
    [[ ${#v} -ge 12 ]] || { log "Password must contain at least 12 characters."; continue; }
    read -r -s -p "Confirm: " c || true; printf '\n'
    [[ "$v" == "$c" ]] || { log "Values do not match."; continue; }
    printf '%s' "$v"; return
  done
}

configure_environment(){
  if [[ ! -f "$PARS2RAY_ENV_FILE" ]]; then
    cp "$PARS2RAY_INSTALL_DIR/.env.example" "$PARS2RAY_ENV_FILE"
    PARS2RAY_FIRST_INSTALL=1
  fi
  chmod 600 "$PARS2RAY_ENV_FILE"
  install -d -m 0750 "$PARS2RAY_DATA_DIR"

  local j m db
  j="$(read_env_value JWT_SECRET)"; [[ -n "$j" && "$j" != replace-with-* ]] || j="$(random_hex)"
  m="$(read_env_value MASTER_SECRET)"; [[ -n "$m" && "$m" != replace-with-* ]] || m="$(random_hex)"
  db="$(read_env_value DATABASE_URL)"; [[ "$db" == sqlite:* ]] || db="sqlite:////${PARS2RAY_DATA_DIR#/}/pars2ray.db"

  set_env_value ENVIRONMENT production
  set_env_value DEBUG false
  set_env_value DATABASE_URL "$db"
  set_env_value REDIS_URL ""
  set_env_value JWT_SECRET "$j"
  set_env_value MASTER_SECRET "$m"
  set_env_value PARS2RAY_DATA_DIR "$PARS2RAY_DATA_DIR"
}

configure_first_run(){
  local u e p port host
  printf '\n=== Pars2Ray Native Installer v2 ===\nNo Docker, PostgreSQL or Redis setup is required.\n\n'
  u="${PARS2RAY_ADMIN_USER:-$(read_env_value ADMIN_USER)}"; u="${u:-$(prompt_value 'Panel username' admin)}"
  [[ "$u" =~ ^[A-Za-z0-9_.-]{3,64}$ ]] || die "Invalid panel username"
  e="${PARS2RAY_ADMIN_EMAIL:-$(read_env_value ADMIN_EMAIL)}"; e="${e:-$(prompt_value 'Panel email' admin@example.com)}"
  [[ "$e" == *@*.* ]] || die "Invalid panel email"
  p="${PARS2RAY_ADMIN_PASSWORD:-}"
  if [[ -z "$p" || "$p" == replace-with-* ]]; then p="$(prompt_secret 'Panel password (minimum 12 characters)')"; fi
  port="${PARS2RAY_PANEL_PORT:-$(read_env_value PANEL_HTTP_PORT)}"; port="${port:-8000}"
  [[ "$port" =~ ^[0-9]+$ ]] && ((port>=1 && port<=65535)) || die "Invalid panel port"
  host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}') }"; host="${host// /}"; host="${host:-localhost}"
  set_env_value ADMIN_USER "$u"
  set_env_value ADMIN_EMAIL "$e"
  set_env_value ADMIN_PASSWORD "$p"
  set_env_value PANEL_HTTP_PORT "$port"
  set_env_value TRUSTED_HOSTS "localhost,127.0.0.1,$host"
}

prepare_python(){
  local venv="$PARS2RAY_INSTALL_DIR/.venv"
  if [[ ! -x "$venv/bin/python" ]]; then python3 -m venv "$venv"; fi
  "$venv/bin/python" -m pip install --upgrade pip wheel >/dev/null
  "$venv/bin/pip" install -r "$PARS2RAY_INSTALL_DIR/master/requirements.txt"
  printf '%s\n' "$venv"
}

migrate_database(){
  local venv="$1" db
  db="$(read_env_value DATABASE_URL)"
  export DATABASE_URL="$db"
  export PYTHONPATH="$PARS2RAY_INSTALL_DIR/master"
  cd "$PARS2RAY_INSTALL_DIR"
  "$venv/bin/alembic" upgrade head
}

write_services(){
  local venv="$1" port="$2" svc=/etc/systemd/system
  cat > "$svc/pars2ray-master.service" <<EOF
[Unit]
Description=Pars2Ray Master Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$PARS2RAY_INSTALL_DIR
EnvironmentFile=$PARS2RAY_ENV_FILE
Environment=PYTHONPATH=$PARS2RAY_INSTALL_DIR/master
ExecStart=$venv/bin/uvicorn app.main:app --app-dir $PARS2RAY_INSTALL_DIR/master --host 0.0.0.0 --port $port --proxy-headers --timeout-keep-alive 15
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$PARS2RAY_DATA_DIR

[Install]
WantedBy=multi-user.target
EOF

  cat > "$svc/pars2ray-worker.service" <<EOF
[Unit]
Description=Pars2Ray Worker
After=network-online.target pars2ray-master.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$PARS2RAY_INSTALL_DIR
EnvironmentFile=$PARS2RAY_ENV_FILE
Environment=PYTHONPATH=$PARS2RAY_INSTALL_DIR/master
ExecStart=$venv/bin/python -m app.worker
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$PARS2RAY_DATA_DIR

[Install]
WantedBy=multi-user.target
EOF

  cat > /usr/local/bin/pars2ray <<EOF
#!/usr/bin/env bash
set -e
case "\${1:-status}" in
  status) systemctl --no-pager --full status pars2ray-master pars2ray-worker ;;
  start) systemctl start pars2ray-master pars2ray-worker ;;
  stop) systemctl stop pars2ray-worker pars2ray-master ;;
  restart) systemctl restart pars2ray-master pars2ray-worker ;;
  logs) journalctl -u pars2ray-master -u pars2ray-worker -n 200 --no-pager ;;
  update) exec $PARS2RAY_INSTALL_DIR/deploy/install.sh ;;
  *) echo 'Usage: pars2ray {status|start|stop|restart|logs|update}'; exit 2 ;;
esac
EOF
  chmod 0755 /usr/local/bin/pars2ray
  systemctl daemon-reload
  systemctl enable pars2ray-master pars2ray-worker >/dev/null
}

start_and_verify(){
  local port="$1" url="http://127.0.0.1:${1}/health" attempt
  systemctl restart pars2ray-master
  for attempt in $(seq 1 45); do
    if curl -fsS --connect-timeout 1 --max-time 2 "$url" >/dev/null 2>&1; then
      log "Master health check passed"
      systemctl restart pars2ray-worker
      return 0
    fi
    ((attempt==1 || attempt%10==0)) && log "Waiting for master ($attempt/45)"
    sleep 1
  done
  journalctl -u pars2ray-master -n 120 --no-pager >&2 || true
  die "Master did not become healthy"
}

main(){
  install_prerequisites
  checkout_project
  configure_environment
  configure_first_run
  local venv; venv="$(prepare_python)"
  migrate_database "$venv"
  local port; port="$(read_env_value PANEL_HTTP_PORT)"; port="${port:-8000}"
  write_services "$venv" "$port"
  start_and_verify "$port"
  local host u; host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}') }"; host="${host// /}"; host="${host:-localhost}"; u="$(read_env_value ADMIN_USER)"
  printf '\n========================================\n Pars2Ray Native v2 is ready\n Panel: http://%s:%s\n User:  %s\n========================================\n\n' "$host" "$port" "$u"
  printf 'Commands: pars2ray status | restart | logs | update\n'
}
main "$@"
