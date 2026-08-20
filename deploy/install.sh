#!/usr/bin/env bash
set -Eeuo pipefail

# Pars2Ray one-command production installer.
# First install is interactive: panel credentials + node inventory are collected.
# All infrastructure secrets are generated automatically and .env is never edited by the user.

PARS2RAY_REPOSITORY="${PARS2RAY_REPOSITORY:-https://github.com/TheOnlyOneWithAi/pars2ray.git}"
PARS2RAY_REF="${PARS2RAY_REF:-main}"
PARS2RAY_INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
PARS2RAY_ENV_FILE="${PARS2RAY_INSTALL_DIR}/.env"
PARS2RAY_GENERATED_ADMIN_PASSWORD=0
PARS2RAY_FIRST_INSTALL=0

log() { printf '[pars2ray] %s\n' "$*"; }
die() { printf '[pars2ray] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == "0" ]] || die "Run as root: curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/deploy/install.sh | bash"
[[ -r /etc/os-release ]] || die "Only Ubuntu and Debian are supported"
# shellcheck disable=SC1091
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
  local key="$1" value="$2" escaped
  case "$value" in *$'\n'*|*$'\r'*) die "$key cannot contain a newline" ;; esac
  escaped="${value//\\/\\\\}"
  escaped="${escaped//|/\\|}"
  escaped="${escaped//&/\\&}"
  if grep -q "^${key}=" "$PARS2RAY_ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$PARS2RAY_ENV_FILE"
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

configure_interactively() {
  local admin_user admin_email admin_password panel_port public_host node_count key ip user pass port i
  [[ "$PARS2RAY_FIRST_INSTALL" == "1" ]] || return 0

  printf '\n=== Pars2Ray first-run setup ===\n'
  printf 'You do NOT need to edit .env. This installer creates it automatically.\n\n'

  admin_user="${PARS2RAY_ADMIN_USER:-$(prompt_value 'Panel username' 'admin')}"
  admin_email="${PARS2RAY_ADMIN_EMAIL:-$(prompt_value 'Panel email' 'admin@example.com')}"
  if [[ -n "${PARS2RAY_ADMIN_PASSWORD:-}" ]]; then
    admin_password="$PARS2RAY_ADMIN_PASSWORD"
  else
    admin_password="$(prompt_secret 'Panel password (minimum 12 characters)')"
  fi
  [[ "${#admin_password}" -ge 12 ]] || die "Admin password must be at least 12 characters"

  panel_port="${PARS2RAY_PANEL_PORT:-$(prompt_value 'Panel HTTP port' '8000')}"
  [[ "$panel_port" =~ ^[0-9]+$ ]] && (( panel_port >= 1 && panel_port <= 65535 )) || die "Invalid panel port"
  public_host="${PARS2RAY_PUBLIC_HOST:-$(prompt_value 'Public host/IP' "$(hostname -I 2>/dev/null | awk '{print $1}')")}"

  set_env_value ADMIN_USER "$admin_user"
  set_env_value ADMIN_EMAIL "$admin_email"
  set_env_value ADMIN_PASSWORD "$admin_password"
  set_env_value PANEL_HTTP_PORT "$panel_port"
  set_env_value TRUSTED_HOSTS "localhost,127.0.0.1,${public_host}"

  node_count="${PARS2RAY_NODE_COUNT:-$(prompt_value 'How many managed nodes do you have?' '0')}"
  [[ "$node_count" =~ ^[0-9]+$ ]] || die "Node count must be a non-negative integer"

  for ((i=1; i<=node_count; i++)); do
    printf '\n--- Node %d/%d ---\n' "$i" "$node_count"
    key="$(prompt_value 'Node key' "NODE${i}")"
    key="$(printf '%s' "$key" | tr '[:lower:]-' '[:upper:]_')"
    [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "Node key must contain only letters, numbers and underscores"
    ip="$(prompt_value 'Node IP/hostname')"
    [[ -n "$ip" ]] || die "Node IP/hostname is required"
    user="$(prompt_value 'SSH username' 'root')"
    port="$(prompt_value 'SSH port' '22')"
    [[ "$port" =~ ^[0-9]+$ ]] || die "Invalid SSH port"
    read -r -s -p "SSH password (leave empty if not required): " pass || true
    printf '\n'

    set_env_value "${key}_IP" "$ip"
    set_env_value "${key}_USER" "$user"
    set_env_value "${key}_PORT" "$port"
    set_env_value "${key}_PASS" "$pass"
  done
}

configure_environment() {
  if [[ ! -f "$PARS2RAY_ENV_FILE" ]]; then
    cp "$PARS2RAY_INSTALL_DIR/.env.example" "$PARS2RAY_ENV_FILE"
  else
    cp "$PARS2RAY_ENV_FILE" "$PARS2RAY_ENV_FILE.backup.$(date -u +%Y%m%d%H%M%S)"
  fi
  chmod 600 "$PARS2RAY_ENV_FILE"

  local postgres_password jwt_secret master_secret admin_password current_host detected_host
  postgres_password="$(read_env_value POSTGRES_PASSWORD)"
  [[ -n "$postgres_password" && "$postgres_password" != replace-with-* ]] || postgres_password="${PARS2RAY_POSTGRES_PASSWORD:-$(random_hex)}"
  jwt_secret="$(read_env_value JWT_SECRET)"
  [[ -n "$jwt_secret" && "$jwt_secret" != replace-with-* ]] || jwt_secret="$(random_hex)"
  master_secret="$(read_env_value MASTER_SECRET)"
  [[ -n "$master_secret" && "$master_secret" != replace-with-* ]] || master_secret="$(random_hex)"
  admin_password="$(read_env_value ADMIN_PASSWORD)"
  if [[ -z "$admin_password" || "$admin_password" == replace-with-* ]]; then
    admin_password="${PARS2RAY_ADMIN_PASSWORD:-$(random_hex)}"
    PARS2RAY_GENERATED_ADMIN_PASSWORD=1
  fi
  [[ "${#admin_password}" -ge 12 ]] || die "Admin password must be at least 12 characters"

  set_env_value POSTGRES_PASSWORD "$postgres_password"
  set_env_value JWT_SECRET "$jwt_secret"
  set_env_value MASTER_SECRET "$master_secret"
  set_env_value ADMIN_PASSWORD "$admin_password"
  set_env_value ENVIRONMENT production
  set_env_value DEBUG false
  set_env_value DATABASE_URL 'postgresql+psycopg://pars2ray:${POSTGRES_PASSWORD}@db:5432/pars2ray'
  set_env_value REDIS_URL 'redis://redis:6379/0'

  current_host="$(read_env_value TRUSTED_HOSTS)"
  detected_host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
  if [[ -z "$current_host" || "$current_host" == "localhost,127.0.0.1" || "$current_host" == "localhost,127.0.0.1,"* ]]; then
    [[ -n "$detected_host" ]] && set_env_value TRUSTED_HOSTS "localhost,127.0.0.1,${detected_host}"
  fi
}

start_and_verify() {
  local port health_url attempt
  port="$(read_env_value PANEL_HTTP_PORT)"
  port="${port:-8000}"
  "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$PARS2RAY_INSTALL_DIR/deploy/docker-compose.yml" config >/dev/null
  "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$PARS2RAY_INSTALL_DIR/deploy/docker-compose.yml" up -d --build
  health_url="http://127.0.0.1:${port}/health"
  for attempt in $(seq 1 45); do
    if curl -fsS --max-time 3 "$health_url" >/dev/null; then
      log "Master health check passed"
      return 0
    fi
    sleep 2
  done
  "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$PARS2RAY_INSTALL_DIR/deploy/docker-compose.yml" ps
  die "Master did not become healthy. Inspect: cd $PARS2RAY_INSTALL_DIR && docker compose logs --tail=200 master"
}

main() {
  local panel_port admin_user public_host
  install_prerequisites
  ensure_docker
  checkout_project
  configure_environment
  configure_interactively
  start_and_verify
  panel_port="$(read_env_value PANEL_HTTP_PORT)"
  panel_port="${panel_port:-8000}"
  admin_user="$(read_env_value ADMIN_USER)"
  admin_user="${admin_user:-admin}"
  public_host="${PARS2RAY_PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
  log "Pars2Ray is installed at $PARS2RAY_INSTALL_DIR"
  log "Panel: http://${public_host}:${panel_port}"
  log "Admin user: ${admin_user}"
  if [[ "$PARS2RAY_GENERATED_ADMIN_PASSWORD" == "1" ]]; then
    log "Generated admin password (store it now): $(read_env_value ADMIN_PASSWORD)"
  else
    log "Admin password configured during first-run setup"
  fi
  log "OpenAPI: http://${public_host}:${panel_port}/docs"
}

main "$@"
