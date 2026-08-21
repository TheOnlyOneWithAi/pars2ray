#!/usr/bin/env bash
set -Eeuo pipefail
PARS2RAY_REPOSITORY="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
PARS2RAY_REF="${PARS2RAY_REF:-main}"
PARS2RAY_INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
PARS2RAY_ENV_FILE="${PARS2RAY_INSTALL_DIR}/.env"
PARS2RAY_APT_MIRROR="${PARS2RAY_APT_MIRROR:-https://mirror.iranserver.com/ubuntu/}"
PARS2RAY_FIRST_INSTALL=0
log(){ printf '[pars2ray] %s\n' "$*"; }
die(){ printf '[pars2ray] ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || die "Run as root"
[[ -r /etc/os-release ]] || die "Only Ubuntu and Debian are supported"; . /etc/os-release
case "${ID:-}" in ubuntu|debian);;*) die "Unsupported distribution: ${ID:-unknown}";;esac
install_prerequisites(){
  export DEBIAN_FRONTEND=noninteractive
  local need=0
  command -v curl >/dev/null || need=1; command -v git >/dev/null || need=1; command -v openssl >/dev/null || need=1
  if (( need )); then
    if [[ "$ID" == ubuntu && -n "$PARS2RAY_APT_MIRROR" ]]; then
      [[ ! -f /etc/apt/sources.list.d/ubuntu.sources ]] || sed -i -E "s#https?://[^[:space:]]+/ubuntu/?#${PARS2RAY_APT_MIRROR%/}#g" /etc/apt/sources.list.d/ubuntu.sources || true
      [[ ! -f /etc/apt/sources.list ]] || sed -i -E "s#https?://(archive|[a-z]+\.archive)\.ubuntu\.com/ubuntu/?#${PARS2RAY_APT_MIRROR%/}#g" /etc/apt/sources.list || true
    fi
    apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=8 -o Acquire::https::Timeout=8 update -qq
    apt-get install -y -qq ca-certificates curl git openssl
  fi
}
ensure_docker(){
  if ! command -v docker >/dev/null; then apt-get install -y -qq docker.io || curl -fsSL --connect-timeout 5 --max-time 20 https://get.docker.com | sh; fi
  command -v systemctl >/dev/null && systemctl list-unit-files docker.service >/dev/null 2>&1 && systemctl enable --now docker || true
  if ! docker compose version >/dev/null 2>&1; then apt-get update -qq; apt-get install -y -qq docker-compose-plugin 2>/dev/null || apt-get install -y -qq docker-compose-v2 2>/dev/null || true; fi
  if docker compose version >/dev/null 2>&1; then PARS2RAY_COMPOSE=(docker compose); elif command -v docker-compose >/dev/null; then PARS2RAY_COMPOSE=(docker-compose); else die "Docker Compose v2 is required"; fi
}
checkout_project(){
  [[ ! -e "$PARS2RAY_INSTALL_DIR" || -d "$PARS2RAY_INSTALL_DIR/.git" ]] || die "$PARS2RAY_INSTALL_DIR exists and is not a Pars2Ray checkout"
  if [[ -d "$PARS2RAY_INSTALL_DIR/.git" ]]; then
    git -C "$PARS2RAY_INSTALL_DIR" diff --quiet || die "Existing checkout has uncommitted changes"
    git -C "$PARS2RAY_INSTALL_DIR" diff --cached --quiet || die "Existing checkout has staged changes"
    git -C "$PARS2RAY_INSTALL_DIR" fetch --depth 1 origin "$PARS2RAY_REF"; git -C "$PARS2RAY_INSTALL_DIR" checkout --force "$PARS2RAY_REF"; git -C "$PARS2RAY_INSTALL_DIR" reset --hard "origin/$PARS2RAY_REF"
  else PARS2RAY_FIRST_INSTALL=1; install -d -m 0755 "$(dirname "$PARS2RAY_INSTALL_DIR")"; git clone --depth 1 --branch "$PARS2RAY_REF" "$PARS2RAY_REPOSITORY" "$PARS2RAY_INSTALL_DIR"; fi
}
read_env_value(){ local key="$1"; [[ -f "$PARS2RAY_ENV_FILE" ]] || return 0; awk -F= -v wanted="$key" '$1==wanted{sub(/^[^=]*=/,"");print;exit}' "$PARS2RAY_ENV_FILE"; }
set_env_value(){ local key="$1" value="$2" tmp="${PARS2RAY_ENV_FILE}.tmp.$$"; case "$value" in *$'\n'*|*$'\r'*) die "$key cannot contain a newline";;esac; awk -v w="$key" -v r="$value" 'BEGIN{f=0}$0~"^"w"="{if(!f){print w"="r;f=1};next}{print}END{if(!f)print w"="r}' "$PARS2RAY_ENV_FILE" > "$tmp"; chmod 600 "$tmp"; mv -f "$tmp" "$PARS2RAY_ENV_FILE"; }
random_hex(){ openssl rand -hex 32; }
prompt_value(){ local p="$1" d="${2:-}" v; read -r -p "$p${d:+ [$d]}: " v || true; printf '%s' "${v:-$d}"; }
prompt_secret(){ local p="$1" v c; while true; do read -r -s -p "$p: " v || true; printf '\n'; [[ -n "$v" ]] || { log "Value cannot be empty."; continue; }; read -r -s -p "Confirm: " c || true; printf '\n'; [[ "$v" == "$c" ]] || { log "Values do not match. Try again."; continue; }; printf '%s' "$v"; return; done; }
configure_environment(){
  [[ -f "$PARS2RAY_ENV_FILE" ]] || cp "$PARS2RAY_INSTALL_DIR/.env.example" "$PARS2RAY_ENV_FILE"; chmod 600 "$PARS2RAY_ENV_FILE"
  local p j m; p="$(read_env_value POSTGRES_PASSWORD)"; [[ -n "$p" && "$p" != replace-with-* ]] || p="${PARS2RAY_POSTGRES_PASSWORD:-$(random_hex)}"; j="$(read_env_value JWT_SECRET)"; [[ -n "$j" && "$j" != replace-with-* ]] || j="$(random_hex)"; m="$(read_env_value MASTER_SECRET)"; [[ -n "$m" && "$m" != replace-with-* ]] || m="$(random_hex)"
  set_env_value POSTGRES_PASSWORD "$p"; set_env_value JWT_SECRET "$j"; set_env_value MASTER_SECRET "$m"; set_env_value ENVIRONMENT production; set_env_value DEBUG false; set_env_value DATABASE_URL 'postgresql+psycopg://pars2ray:${POSTGRES_PASSWORD}@db:5432/pars2ray?connect_timeout=5'; set_env_value REDIS_URL 'redis://redis:6379/0'
}
configure_first_run(){
  [[ "$PARS2RAY_FIRST_INSTALL" == 1 ]] || return 0; local u e p port host
  printf '\n=== Pars2Ray first-run setup ===\nYou do NOT need to edit .env.\n\n'; u="${PARS2RAY_ADMIN_USER:-$(prompt_value 'Panel username' admin)}"; [[ "$u" =~ ^[A-Za-z0-9_.-]{3,64}$ ]] || die "Invalid panel username"; e="${PARS2RAY_ADMIN_EMAIL:-$(prompt_value 'Panel email' admin@example.com)}"; [[ "$e" == *@*.* ]] || die "Invalid panel email"; p="${PARS2RAY_ADMIN_PASSWORD:-$(prompt_secret 'Panel password (minimum 12 characters)')}"; (( ${#p} >= 12 )) || die "Admin password must be at least 12 characters"; port="${PARS2RAY_PANEL_PORT:-$(prompt_value 'Panel HTTP port' 8000)}"; [[ "$port" =~ ^[0-9]+$ ]] && ((port>=1&&port<=65535)) || die "Invalid panel port"; host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null|awk '{print $1}') }"; host="${host// /}"; [[ -n "$host" ]] || host=localhost; set_env_value ADMIN_USER "$u"; set_env_value ADMIN_EMAIL "$e"; set_env_value ADMIN_PASSWORD "$p"; set_env_value PANEL_HTTP_PORT "$port"; set_env_value TRUSTED_HOSTS "localhost,127.0.0.1,$host"
}
start_and_verify(){
  local port url attempt compose_file="$PARS2RAY_INSTALL_DIR/deploy/docker-compose.yml"; port="$(read_env_value PANEL_HTTP_PORT)"; port="${port:-8000}"; "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" config >/dev/null
  log "Pre-pulling database images"; "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" pull db redis >/dev/null 2>&1 & local pid=$!; "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" build --pull=false master; wait "$pid" || log "Pre-pull failed; compose will retry"
  "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" up -d; url="http://127.0.0.1:${port}/health"; log "Waiting for master health: $url"
  for attempt in $(seq 1 45); do curl -fsS --connect-timeout 1 --max-time 2 "$url" >/dev/null 2>&1 && { log "Master health check passed"; return; }; ((attempt==1||attempt%10==0)) && log "Health not ready yet ($attempt/45)"; sleep 1; done
  printf '\n[pars2ray] Master diagnostics:\n' >&2; "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" ps >&2 || true; "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" logs --tail=160 master >&2 || true; "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" logs --tail=60 db >&2 || true; die "Master did not become healthy"
}
main(){ install_prerequisites; ensure_docker; checkout_project; configure_environment; configure_first_run; start_and_verify; local port u host; port="$(read_env_value PANEL_HTTP_PORT)"; port="${port:-8000}"; u="$(read_env_value ADMIN_USER)"; u="${u:-admin}"; host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null|awk '{print $1}') }"; host="${host// /}"; [[ -n "$host" ]] || host=localhost; printf '\n========================================\n Pars2Ray is ready\n Panel: http://%s:%s\n User:  %s\n========================================\n' "$host" "$port" "$u"; printf 'Manage Nodes from Panel -> Nodes -> Add Node.\nThe installer never requires manual .env editing.\n\n'; }
main "$@"
