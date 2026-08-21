#!/usr/bin/env bash
set -Eeuo pipefail

# Pars2Ray one-command production installer.
# Fresh install is interactive for the panel account only; all infrastructure
# secrets are generated automatically. Users never need to edit .env.

PARS2RAY_REPOSITORY="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
PARS2RAY_REF="${PARS2RAY_REF:-main}"
PARS2RAY_INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
PARS2RAY_ENV_FILE="${PARS2RAY_INSTALL_DIR}/.env"
PARS2RAY_FIRST_INSTALL=0

log() { printf '[pars2ray] %s\n' "$*"; }
die() { printf '[pars2ray] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == "0" ]] || die "Run as root: curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/deploy/install.sh | bash"
[[ -r /etc/os-release ]] || die "Only Ubuntu and Debian are supported"
. /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *) die "Unsupported distribution: ${ID:-unknown}. Use Ubuntu or Debian." ;;
esac

install_prerequisites() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git openssl
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker Engine"
    if ! apt-get install -y -qq docker.io; then
      curl -fsSL https://get.docker.com | sh
    fi
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files docker.service >/dev/null 2>&1; then
    systemctl enable --now docker
  fi
  if ! docker compose version >/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-plugin 2>/dev/null || apt-get install -y -qq docker-compose-v2 2>/dev/null || true
  fi
  if docker compose version >/dev/null 2>&1; then
    PARS2RAY_COMPOSE=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    PARS2RAY_COMPOSE=(docker-compose)
  else
    die "Docker Compose v2 is required but was not found"
  fi
}

checkout_project() {
  if [[ -e "$PARS2RAY_INSTALL_DIR" && ! -d "$PARS2RAY_INSTALL_DIR/.git" ]]; then
    die "$PARS2RAY_INSTALL_DIR exists and is not a Pars2Ray checkout"
  fi
  if [[ -d "$PARS2RAY_INSTALL_DIR/.git" ]]; then
    git -C "$PARS2RAY_INSTALL_DIR" diff --quiet || die "Existing checkout has uncommitted changes"
    git -C "$PARS2RAY_INSTALL_DIR" diff --cached --quiet || die "Existing checkout has staged changes"
    git -C "$PARS2RAY_INSTALL_DIR" fetch --depth 1 origin "$PARS2RAY_REF"
    git -C "$PARS2RAY_INSTALL_DIR" checkout --force "$PARS2RAY_REF"
    git -C "$PARS2RAY_INSTALL_DIR" reset --hard "origin/$PARS2RAY_REF"
  else
    PARS2RAY_FIRST_INSTALL=1
    install -d -m 0755 "$(dirname "$PARS2RAY_INSTALL_DIR")"
    git clone --depth 1 --branch "$PARS2RAY_REF" "$PARS2RAY_REPOSITORY" "$PARS2RAY_INSTALL_DIR"
  fi
}

read_env_value() {
  local key="$1"
  [[ -f "$PARS2RAY_ENV_FILE" ]] || return 0
  awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$PARS2RAY_ENV_FILE"
}

set_env_value() {
  local key="$1" value="$2"
  case "$value" in *$'\n'*|*$'\r'*) die "$key cannot contain a newline" ;; esac
  if grep -q "^${key}=" "$PARS2RAY_ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$PARS2RAY_ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$PARS2RAY_ENV_FILE"
  fi
}

random_hex() { openssl rand -hex 32; }

prompt_value() {
  local prompt="$1" default="${2:-}" value
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " value || true
    printf '%s' "${value:-$default}"
  else
    read -r -p "$prompt: " value || true
    printf '%s' "$value"
  fi
}

prompt_secret() {
  local prompt="$1" value confirmation
  while true; do
    read -r -s -p "$prompt: " value || true
    printf '\n'
    [[ -n "$value" ]] || { log "Value cannot be empty."; continue; }
    read -r -s -p "Confirm: " confirmation || true
    printf '\n'
    [[ "$value" == "$confirmation" ]] || { log "Values do not match. Try again."; continue; }
    printf '%s' "$value"
    return 0
  done
}

configure_environment() {
  if [[ ! -f "$PARS2RAY_ENV_FILE" ]]; then
    cp "$PARS2RAY_INSTALL_DIR/.env.example" "$PARS2RAY_ENV_FILE"
  else
    cp "$PARS2RAY_ENV_FILE" "$PARS2RAY_ENV_FILE.backup.$(date -u +%Y%m%d%H%M%S)"
  fi
  chmod 600 "$PARS2RAY_ENV_FILE"

  local postgres_password jwt_secret master_secret
  postgres_password="$(read_env_value POSTGRES_PASSWORD)"
  [[ -n "$postgres_password" && "$postgres_password" != replace-with-* ]] || postgres_password="${PARS2RAY_POSTGRES_PASSWORD:-$(random_hex)}"
  jwt_secret="$(read_env_value JWT_SECRET)"
  [[ -n "$jwt_secret" && "$jwt_secret" != replace-with-* ]] || jwt_secret="$(random_hex)"
  master_secret="$(read_env_value MASTER_SECRET)"
  [[ -n "$master_secret" && "$master_secret" != replace-with-* ]] || master_secret="$(random_hex)"

  set_env_value POSTGRES_PASSWORD "$postgres_password"
  set_env_value JWT_SECRET "$jwt_secret"
  set_env_value MASTER_SECRET "$master_secret"
  set_env_value ENVIRONMENT production
  set_env_value DEBUG false
  set_env_value DATABASE_URL 'postgresql+psycopg://pars2ray:${POSTGRES_PASSWORD}@db:5432/pars2ray'
  set_env_value REDIS_URL 'redis://redis:6379/0'
}

configure_first_run() {
  [[ "$PARS2RAY_FIRST_INSTALL" == "1" ]] || return 0
  local admin_user admin_email admin_password panel_port public_host
  printf '\n=== Pars2Ray first-run setup ===\n'
  printf 'You do NOT need to edit .env. Everything else is generated automatically.\n\n'

  admin_user="${PARS2RAY_ADMIN_USER:-$(prompt_value 'Panel username' 'admin')}"
  [[ "$admin_user" =~ ^[A-Za-z0-9_.-]{3,64}$ ]] || die "Invalid panel username"
  admin_email="${PARS2RAY_ADMIN_EMAIL:-$(prompt_value 'Panel email' 'admin@example.com')}"
  [[ "$admin_email" == *@*.* ]] || die "Invalid panel email"
  if [[ -n "${PARS2RAY_ADMIN_PASSWORD:-}" ]]; then
    admin_password="$PARS2RAY_ADMIN_PASSWORD"
  else
    admin_password="$(prompt_secret 'Panel password (minimum 12 characters)')"
  fi
  [[ "${#admin_password}" -ge 12 ]] || die "Admin password must be at least 12 characters"

  panel_port="${PARS2RAY_PANEL_PORT:-$(prompt_value 'Panel HTTP port' '8000')}"
  [[ "$panel_port" =~ ^[0-9]+$ ]] && (( panel_port >= 1 && panel_port <= 65535 )) || die "Invalid panel port"
  public_host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}') }"
  public_host="${public_host// /}"
  [[ -n "$public_host" ]] || public_host="localhost"

  set_env_value ADMIN_USER "$admin_user"
  set_env_value ADMIN_EMAIL "$admin_email"
  set_env_value ADMIN_PASSWORD "$admin_password"
  set_env_value PANEL_HTTP_PORT "$panel_port"
  set_env_value TRUSTED_HOSTS "localhost,127.0.0.1,${public_host}"
}

start_and_verify() {
  local port health_url attempt compose_file="$PARS2RAY_INSTALL_DIR/deploy/docker-compose.yml"
  port="$(read_env_value PANEL_HTTP_PORT)"
  port="${port:-8000}"
  "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" config >/dev/null
  "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" up -d --build
  health_url="http://127.0.0.1:${port}/health"
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 3 "$health_url" >/dev/null; then
      log "Master health check passed"
      return 0
    fi
    sleep 2
  done
  "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$compose_file" ps
  die "Master did not become healthy. Inspect: cd $PARS2RAY_INSTALL_DIR && docker compose logs --tail=200 master"
}

main() {
  local panel_port admin_user public_host
  install_prerequisites
  ensure_docker
  checkout_project
  configure_environment
  configure_first_run
  start_and_verify

  panel_port="$(read_env_value PANEL_HTTP_PORT)"
  panel_port="${panel_port:-8000}"
  admin_user="$(read_env_value ADMIN_USER)"
  admin_user="${admin_user:-admin}"
  public_host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}') }"
  public_host="${public_host// /}"
  [[ -n "$public_host" ]] || public_host="localhost"

  printf '\n========================================\n'
  printf ' Pars2Ray is ready\n'
  printf ' Panel: http://%s:%s\n' "$public_host" "$panel_port"
  printf ' User:  %s\n' "$admin_user"
  printf '========================================\n'
  printf 'Manage Nodes from Panel -> Nodes -> Add Node.\n'
  printf 'The installer never requires manual .env editing.\n\n'
}

main "$@"
