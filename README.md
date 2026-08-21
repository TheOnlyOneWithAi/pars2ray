# Pars2Ray Enterprise

[English](README.md) | [فارسی](README.fa.md) | [Русский](README.ru.md)

Pars2Ray is a production-oriented network orchestration control plane with one FastAPI master, PostgreSQL persistence, Redis service, background worker, React/TypeScript console, and authenticated lightweight node agents.

## Repository

```text
master/       FastAPI control plane, domain services, persistence, worker
agent/        node-only agent; no UI or database
frontend/     React + TypeScript enterprise console
migrations/   Alembic migration environment and initial schema
installer/    SSH bootstrap for nodes
deploy/       Docker Compose, installer, CLI and backup scripts
tests/        deterministic backend tests
```

## One-command installation

Pars2Ray is designed to install like a panel: **one command, no manual `.env` editing**.

```bash
curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/install.sh | sudo bash
```

The installer automatically installs Docker/Compose when needed, downloads the current release, generates runtime secrets, detects a safe Docker subnet, asks only for the panel account/port, starts PostgreSQL + Redis + Master + Worker, runs migrations, verifies the panel, and prints the final URL. Existing installations keep their `.env` and data.

You can also use the installer directly:

```bash
curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/deploy/install.sh | sudo bash
```

After installation, management is intentionally simple:

```bash
pars2ray status
pars2ray restart
pars2ray logs
pars2ray update
```

Useful commands are `start`, `stop`, `restart`, `status`, `logs`, `master-logs`, `worker-logs`, `update`, `config`, `install`, and `uninstall`.

### What the installer asks

On a first install, it asks interactively for:

1. Panel username
2. Panel email
3. Panel password
4. Panel HTTP port

PostgreSQL password, JWT secret, master secret and the Docker network are generated automatically. **Do not create or edit `.env` manually.**

The panel is then available at `http://SERVER_IP:PORT/`. The initial Super Admin is created from the values entered by the installer.

## Manual development setup

For development only, you can still create `.env` manually and start Compose:

```bash
cp .env.example .env
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

## Features

The control panel includes live traffic telemetry, node command workflows, route activation, protocol inventory, experiment promotion, guarded optimizer runs, RBAC user administration, subscriptions, plans, API keys, runtime settings, optional AI controls, and audit events. English, Persian (RTL), and Russian are available from the panel language selector.

## Verification

```bash
PYTHONPATH=master pytest -q tests
python -m compileall -q master/app agent/app installer
cd frontend && npm ci && npm run typecheck && npm run build
```

Operational deployment steps are in [DEPLOYMENT.md](DEPLOYMENT.md). Architecture and threat controls are in [ARCHITECTURE.md](ARCHITECTURE.md) and [SECURITY.md](SECURITY.md).
