#!/usr/bin/env bash
set -Eeuo pipefail

# Pars2Ray production installer.
# Optional inputs: PARS2RAY_INSTALL_DIR, PARS2RAY_REF,
# PARS2RAY_PUBLIC_HOST, PARS2RAY_ADMIN_PASSWORD, PARS2RAY_POSTGRES_PASSWORD.

PARS2RAY_REPOSITORY="${PARS2RAY_REPOSITORY:-https://github.com/parsahoseini549-star/pars2ray.git}"
PARS2RAY_REF="${PARS2RAY_REF:-main}"
PARS2RAY_INSTALL_DIR="${PARS2RAY_INSTALL_DIR:-/opt/pars2ray}"
PARS2RAY_ENV_FILE="${PARS2RAY_INSTALL_DIR}/.env"
PARS2RAY_GENERATED_ADMIN_PASSWORD=0

log() { printf '[pars2ray] %s\n' "$*"; }
die() { printf '[pars2ray] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == "0" ]] || die "Run as root: curl -fsSL ... | sudo bash"
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
  for attempt in $(seq 1 30); do
    if curl -fsS --max-time 3 "$health_url" >/dev/null; then
      log "Master health check passed"
      return 0
    fi
    sleep 2
  done
  "${PARS2RAY_COMPOSE[@]}" --env-file "$PARS2RAY_ENV_FILE" -f "$PARS2RAY_INSTALL_DIR/deploy/docker-compose.yml" ps
  die "Master did not become healthy. Inspect container logs with: cd $PARS2RAY_INSTALL_DIR && docker compose logs --tail=200 master"
}

main() {
  local panel_port admin_user public_host
  install_prerequisites
  ensure_docker
  checkout_project
  configure_environment
  start_and_verify
  panel_port="$(read_env_value PANEL_HTTP_PORT)"
  panel_port="${panel_port:-8000}"
  admin_user="$(read_env_value ADMIN_USER)"
  admin_user="${admin_user:-admin}"
  public_host="${PARS2RAY_PUBLIC_HOST:-127.0.0.1}"
  log "Pars2Ray is installed at $PARS2RAY_INSTALL_DIR"
  log "Panel: http://${public_host}:${panel_port}"
  log "Admin user: ${admin_user}"
  if [[ "$PARS2RAY_GENERATED_ADMIN_PASSWORD" == "1" ]]; then
    log "Generated admin password (store it now): $(read_env_value ADMIN_PASSWORD)"
  else
    log "Existing admin password was preserved"
  fi
  log "OpenAPI: http://${public_host}:${panel_port}/docs"
}

main "$@"
