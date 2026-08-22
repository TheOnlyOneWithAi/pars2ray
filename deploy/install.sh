#!/usr/bin/env bash
set -Eeuo pipefail

APP="pars2ray"
INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
DATA_DIR="${PARS2RAY_DATA_DIR:-${INSTALL_DIR}/data}"
ETC_DIR="/etc/pars2ray"
ENV_FILE="${ETC_DIR}/pars2ray.env"
CREDENTIALS_FILE="${ETC_DIR}/credentials"
CLI_SOURCE="${INSTALL_DIR}/deploy/pars2ray"
REPOSITORY="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
REF="${PARS2RAY_REF:-main}"
PORT="${PARS2RAY_PANEL_PORT:-8000}"
VENV_DIR="${INSTALL_DIR}/.venv"
SERVICE_USER="pars2ray"
APT_TIMEOUT="${PARS2RAY_APT_TIMEOUT:-180}"
NETWORK_TIMEOUT="${PARS2RAY_NETWORK_TIMEOUT:-180}"
PIP_TIMEOUT="${PARS2RAY_PIP_TIMEOUT:-300}"

log(){ printf '\033[1;36m[pars2ray]\033[0m %s\n' "$*"; }
ok(){ printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m  !\033[0m %s\n' "$*" >&2; }
die(){ printf '\033[1;31m[pars2ray] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || die "Run as root."
[[ -r /etc/os-release ]] || die "Cannot identify the operating system."
. /etc/os-release
case "${ID:-}" in ubuntu|debian) ;; *) die "Supported distributions: Ubuntu and Debian. Detected: ${ID:-unknown}";; esac
command_exists(){ command -v "$1" >/dev/null 2>&1; }
random_hex(){ openssl rand -hex 32; }
require_timeout(){ command_exists timeout || die "The 'timeout' command is required."; }
read_env(){ local key="$1"; [[ -f "$ENV_FILE" ]] || return 0; awk -F= -v k="$key" '$1==k{sub(/^[^=]*=/,"" ); print; exit}' "$ENV_FILE"; }
set_env(){ local key="$1" value="$2" tmp; case "$value" in *$'\n'*|*$'\r'*) die "$key contains a newline";; esac; install -d -m 0750 "$ETC_DIR"; touch "$ENV_FILE"; tmp="${ENV_FILE}.tmp.$$"; awk -v k="$key" -v v="$value" 'BEGIN{done=0} $0 ~ "^" k "=" {if(!done){print k "=" v;done=1};next} {print} END{if(!done)print k "=" v}' "$ENV_FILE" > "$tmp"; chmod 0600 "$tmp"; mv -f "$tmp" "$ENV_FILE"; }

apt_common_args=(-o Acquire::Retries=3 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 -o DPkg::Lock::Timeout=120)
APT_SOURCES_FILE="${TMPDIR:-/tmp}/pars2ray-apt-sources.list"
configure_reliable_apt_sources(){ local codename="${VERSION_CODENAME:-}"; [[ -n "$codename" ]] || codename="$(lsb_release -cs 2>/dev/null || true)"; [[ -n "$codename" ]] || die "Could not determine distribution codename."; case "${ID:-}" in ubuntu) cat > "$APT_SOURCES_FILE" <<EOF
# Managed temporarily by Pars2Ray installer. Official Ubuntu archives only.
deb https://archive.ubuntu.com/ubuntu ${codename} main restricted universe multiverse
deb https://archive.ubuntu.com/ubuntu ${codename}-updates main restricted universe multiverse
deb https://security.ubuntu.com/ubuntu ${codename}-security main restricted universe multiverse
EOF
;; debian) cat > "$APT_SOURCES_FILE" <<EOF
# Managed temporarily by Pars2Ray installer. Official Debian archives only.
deb https://deb.debian.org/debian ${codename} main
deb https://deb.debian.org/debian ${codename}-updates main
deb https://security.debian.org/debian-security ${codename}-security main
EOF
;; esac; chmod 0644 "$APT_SOURCES_FILE"; }
run_bounded(){ local seconds="$1" label="$2" log_file="$3" rc; shift 3; log "$label (timeout: ${seconds}s)"; if timeout --foreground --kill-after=10s "${seconds}s" "$@" >"$log_file" 2>&1; then return 0; else rc=$?; fi; warn "$label failed or timed out (exit $rc). Diagnostic output:"; tail -n 120 "$log_file" >&2 || true; return "$rc"; }
install_packages(){
 export DEBIAN_FRONTEND=noninteractive; require_timeout; command_exists apt-get || die "apt-get is required"; command_exists dpkg || die "dpkg is required"; command_exists tail || die "tail is required"; configure_reliable_apt_sources; trap 'rm -f "$APT_SOURCES_FILE"' EXIT
 local dpkg_log="${TMPDIR:-/tmp}/pars2ray-dpkg.$$" apt_log="${TMPDIR:-/tmp}/pars2ray-apt.$$" args=(-o Dir::Etc::sourcelist="$APT_SOURCES_FILE" -o Dir::Etc::sourceparts="-" -o APT::Get::List-Cleanup="0"); local audit; audit="$(dpkg --audit 2>&1 || true)"; if [[ -n "$audit" ]]; then run_bounded 120 "Repairing dpkg state" "$dpkg_log" dpkg --configure -a || die "dpkg repair failed"; fi; run_bounded "$APT_TIMEOUT" "Updating APT package indexes" "$apt_log" apt-get "${apt_common_args[@]}" "${args[@]}" update || die "Could not update APT package indexes"; run_bounded "$APT_TIMEOUT" "Installing required system packages" "$apt_log" apt-get "${apt_common_args[@]}" "${args[@]}" install -y ca-certificates curl git openssl python3 python3-venv python3-pip nginx certbot || die "Required packages could not be installed"; rm -f "$dpkg_log" "$apt_log"; ok "System prerequisites ready";
}
fetch_source(){ local git_log="${TMPDIR:-/tmp}/pars2ray-git.$$"; if [[ -d "$INSTALL_DIR/.git" ]]; then run_bounded "$NETWORK_TIMEOUT" "Fetching source from $REPOSITORY [$REF]" "$git_log" git -C "$INSTALL_DIR" fetch --depth 1 origin "$REF" || die "Could not fetch source"; git -C "$INSTALL_DIR" reset --hard "origin/$REF" >/dev/null || die "Could not reset source"; git -C "$INSTALL_DIR" clean -fd >/dev/null || die "Could not clean source"; elif [[ -e "$INSTALL_DIR" ]]; then die "$INSTALL_DIR exists and is not a Git checkout"; else install -d -m 0755 "$(dirname "$INSTALL_DIR")"; run_bounded "$NETWORK_TIMEOUT" "Cloning $REPOSITORY [$REF]" "$git_log" git clone --depth 1 --branch "$REF" "$REPOSITORY" "$INSTALL_DIR" || die "Could not clone source"; fi; rm -f "$git_log"; ok "Source ready"; }
ensure_defaults(){ install -d -m 0750 "$ETC_DIR" "$DATA_DIR"; touch "$ENV_FILE"; chmod 0600 "$ENV_FILE"; local jwt master db host; jwt="$(read_env JWT_SECRET)"; [[ -n "$jwt" ]] || jwt="$(random_hex)"; master="$(read_env MASTER_SECRET)"; [[ -n "$master" ]] || master="$(random_hex)"; db="$(read_env DATABASE_URL)"; [[ "$db" == sqlite:* ]] || db="sqlite:////${DATA_DIR#/}/pars2ray.db"; host="$(hostname -I 2>/dev/null | awk '{print $1}')"; host="${host:-127.0.0.1}"; set_env ENVIRONMENT production; set_env DEBUG false; set_env DATABASE_URL "$db"; set_env REDIS_URL ""; set_env JWT_SECRET "$jwt"; set_env MASTER_SECRET "$master"; set_env PARS2RAY_DATA_DIR "$DATA_DIR"; set_env PANEL_HTTP_PORT "$PORT"; set_env TRUSTED_HOSTS "localhost,127.0.0.1,$host"; }
prompt(){ local label="$1" default="${2:-}" value; if [[ -n "${PARS2RAY_NONINTERACTIVE:-}" || ! -t 0 ]]; then printf '%s' "$default"; return; fi; read -r -p "$label${default:+ [$default]}: " value || true; printf '%s' "${value:-$default}"; }
prompt_password(){ local value confirm; if [[ -n "${PARS2RAY_ADMIN_PASSWORD:-}" ]]; then printf '%s' "$PARS2RAY_ADMIN_PASSWORD"; return; fi; if [[ -n "${PARS2RAY_NONINTERACTIVE:-}" || ! -t 0 ]]; then printf '%s' "$(random_hex)$(random_hex)"; return; fi; while :; do read -r -s -p "Panel password (12+ chars): " value || true; printf '\n'; (( ${#value} >= 12 )) || { warn "Password must be at least 12 characters."; continue; }; read -r -s -p "Confirm password: " confirm || true; printf '\n'; [[ "$value" == "$confirm" ]] || { warn "Passwords do not match."; continue; }; printf '%s' "$value"; return; done; }
first_run(){ local existing_user user email password host; existing_user="$(read_env ADMIN_USER)"; if [[ -n "$existing_user" ]]; then ok "Existing installation detected; keeping panel credentials and settings"; return; fi; printf '\n\033[1;35m=== Pars2Ray setup ===\033[0m\n'; user="${PARS2RAY_ADMIN_USER:-$(prompt 'Username' 'admin')}"; [[ "$user" =~ ^[A-Za-z0-9_.-]{3,64}$ ]] || die "Invalid username"; email="${PARS2RAY_ADMIN_EMAIL:-$(prompt 'Email' 'admin@localhost')}"; [[ "$email" == *@*.* || "$email" == *@localhost ]] || die "Invalid email address"; password="$(prompt_password)"; host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}') }"; host="${host// /}"; host="${host:-localhost}"; set_env ADMIN_USER "$user"; set_env ADMIN_EMAIL "$email"; set_env ADMIN_PASSWORD "$password"; set_env PANEL_HTTP_PORT "$PORT"; set_env TRUSTED_HOSTS "localhost,127.0.0.1,$host"; cat > "$CREDENTIALS_FILE" <<EOF
Pars2Ray installation
=====================
Panel: http://${host}:${PORT}
Username: ${user}
Password: ${password}

Keep this file private. It is readable only by root.
EOF
 chmod 0600 "$CREDENTIALS_FILE"; ok "Panel account configured"; }
setup_python(){ VENV_DIR="${INSTALL_DIR}/.venv"; require_timeout; [[ -x "$VENV_DIR/bin/python" ]] || python3 -m venv "$VENV_DIR" || die "Could not create Python virtual environment"; local pip_log="${TMPDIR:-/tmp}/pars2ray-pip.$$"; run_bounded "$PIP_TIMEOUT" "Upgrading pip/wheel" "$pip_log" "$VENV_DIR/bin/python" -m pip install --upgrade pip wheel || die "Could not upgrade pip/wheel"; run_bounded "$PIP_TIMEOUT" "Installing Python dependencies" "$pip_log" "$VENV_DIR/bin/pip" install -q -r "$INSTALL_DIR/master/requirements.txt" || die "Python dependency installation failed"; rm -f "$pip_log"; ok "Application dependencies ready"; }
migrate(){ local venv="$1" migrate_log="${TMPDIR:-/tmp}/pars2ray-migrate.$$"; [[ -r "$ENV_FILE" ]] || die "Pars2Ray environment file is missing"; set -a; . "$ENV_FILE"; set +a; export DATABASE_URL="$(read_env DATABASE_URL)"; export PYTHONPATH="$INSTALL_DIR/master"; [[ -n "${JWT_SECRET:-}" && -n "${MASTER_SECRET:-}" && -n "${ADMIN_PASSWORD:-}" ]] || die "Required application secrets are missing"; cd "$INSTALL_DIR"; run_bounded 120 "Applying database migrations" "$migrate_log" "$venv/bin/alembic" upgrade head || die "Database migration failed"; rm -f "$migrate_log"; ok "Database ready"; }

write_services(){
  local venv="$1"
  if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin --user-group "$SERVICE_USER" || die "Could not create service account"
  fi
  install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$DATA_DIR"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
  cat > /etc/systemd/system/pars2ray-master.service <<EOF
[Unit]
Description=Pars2Ray Master Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONPATH=$INSTALL_DIR/master
ExecStart=$venv/bin/uvicorn app.main:app --app-dir $INSTALL_DIR/master --host 127.0.0.1 --port $PORT --proxy-headers --timeout-keep-alive 30 --limit-concurrency 1024
Restart=on-failure
RestartSec=3
LimitNOFILE=65535
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
UMask=0077
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
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
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONPATH=$INSTALL_DIR/master
ExecStart=$venv/bin/python -m app.worker
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
UMask=0077
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable pars2ray-master pars2ray-worker >/dev/null || die "Could not enable Pars2Ray services"

  install -d -m 0755 /etc/nginx/conf.d /etc/nginx/sites-enabled /var/www/letsencrypt "$DATA_DIR"
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
        proxy_set_header Connection \"upgrade\";
    }
    location ~ /\\. {
        deny all;
    }
}
EOF
  cat > /etc/nginx/conf.d/pars2ray.conf <<EOF
include ${DATA_DIR}/panel-nginx.conf;
EOF
  rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

  if nginx -t >/tmp/pars2ray-nginx-test.$$ 2>&1; then
    if systemctl enable nginx >/dev/null 2>&1 && systemctl restart nginx >/dev/null 2>&1; then
      ok "nginx reverse proxy installed and running"
    else
      warn "nginx is installed but could not be started; Pars2Ray services and CLI will continue"
      tail -n 80 /tmp/pars2ray-nginx-test.$$ >&2 || true
    fi
  else
    warn "nginx configuration is invalid; leaving nginx stopped and continuing with Pars2Ray"
    tail -n 80 /tmp/pars2ray-nginx-test.$$ >&2 || true
  fi
  rm -f /tmp/pars2ray-nginx-test.$$
}

install_cli(){
  [[ -f "$CLI_SOURCE" ]] || die "Management CLI source missing: $CLI_SOURCE"
  install -m 0755 "$CLI_SOURCE" /usr/local/bin/pars2ray
  [[ -x /usr/local/bin/pars2ray ]] || die "Could not install management CLI"
  /usr/local/bin/pars2ray help >/dev/null 2>&1 || die "Installed pars2ray CLI failed its self-check"
  ok "Management CLI installed: pars2ray change-password"
}

tune_network(){ [[ "${PARS2RAY_TUNE_NETWORK:-1}" == "1" ]] || return 0; command_exists sysctl || return 0; local available current; available="$(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null || true)"; if grep -qw bbr <<<"$available"; then current="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"; [[ "$current" == bbr ]] || sysctl -w net.ipv4.tcp_congestion_control=bbr >/dev/null 2>&1 || true; cat > /etc/sysctl.d/99-pars2ray-network.conf <<'EOF'
net.ipv4.tcp_congestion_control=bbr
EOF
 sysctl --system >/dev/null 2>&1 || true; ok "TCP BBR enabled for supported kernels"; fi; }
health_check(){ local attempt url="http://127.0.0.1:${PORT}/health"; systemctl restart pars2ray-master || { journalctl -u pars2ray-master -n 100 --no-pager >&2 || true; die "Could not start Pars2Ray master service"; }; for attempt in $(seq 1 45); do if curl -fsS --connect-timeout 1 --max-time 2 "$url" >/dev/null 2>&1; then ok "Panel is responding"; systemctl restart pars2ray-worker || { journalctl -u pars2ray-worker -n 100 --no-pager >&2 || true; die "Could not start Pars2Ray worker service"; }; return 0; fi; sleep 1; done; journalctl -u pars2ray-master -n 100 --no-pager >&2 || true; die "Panel did not become ready. Run: pars2ray logs"; }
print_result(){ local host user; host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}') }"; host="${host// /}"; host="${host:-localhost}"; user="$(read_env ADMIN_USER)"; printf '\n\033[1;32m==============================================\033[0m\n Pars2Ray is installed and running\n==============================================\n Panel:       http://%s:%s\n Username:    %s\n Credentials: %s\n CLI:         pars2ray change-password\n Logs:        pars2ray logs\n\n' "$host" "$PORT" "$user" "$CREDENTIALS_FILE"; }
main(){ install_packages; fetch_source; ensure_defaults; first_run; setup_python; migrate "$VENV_DIR"; install_cli; write_services "$VENV_DIR"; tune_network; health_check; print_result; }
main "$@"
