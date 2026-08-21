# Pars2Ray Enterprise

[English](README.md) | [فارسی](README.fa.md) | [Русский](README.ru.md)

Pars2Ray is a production-oriented network orchestration control plane with one FastAPI master, a background worker, a React/TypeScript console, and authenticated lightweight node agents.

## Repository

```text
master/       FastAPI control plane, domain services, persistence, worker
agent/        node-only agent; no UI or database
frontend/     React + TypeScript enterprise console
migrations/   Alembic migration environment and schema
installer/    SSH bootstrap for nodes
deploy/       Native Installer v2, systemd services and legacy Docker files
tests/        deterministic backend tests
```

## One-command Native installation

Pars2Ray now installs without Docker, PostgreSQL, Redis, or manual `.env` editing.

```bash
curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/deploy/install.sh | sudo bash
```

Native Installer v2 automatically installs Python/venv prerequisites, downloads the current release, generates runtime secrets, creates a local SQLite database, runs Alembic migrations, creates `pars2ray-master` and `pars2ray-worker` systemd services, verifies `/health`, and prints the panel URL.

On first install it asks only for:

1. Panel username
2. Panel email
3. Panel password
4. Panel HTTP port

The installer writes the runtime configuration with mode `600`. You do not need to edit `.env` manually.

### Management

```bash
pars2ray status
pars2ray restart
pars2ray logs
pars2ray update
```

### Data

The default database is:

```text
/opt/pars2ray/data/pars2ray.db
```

You can override `PARS2RAY_INSTALL_DIR` and `PARS2RAY_DATA_DIR` before installation. PostgreSQL remains supported for explicit/custom deployments by supplying a PostgreSQL `DATABASE_URL`; it is no longer required by the standard installer.

## Legacy Docker deployment

The Docker Compose files remain in `deploy/docker-compose.yml` for compatibility with existing deployments, but they are no longer used by the standard installer.

## Manual development setup

For development, install Python dependencies from `master/requirements.txt`, set `DATABASE_URL` to a local SQLite URL, and run Alembic before starting the application.

## Features

The control panel includes live traffic telemetry, node command workflows, route activation, protocol inventory, experiment promotion, guarded optimizer runs, RBAC user administration, subscriptions, plans, API keys, runtime settings, optional AI controls, and audit events. English, Persian (RTL), and Russian are available from the panel language selector.

## Verification

```bash
PYTHONPATH=master pytest -q tests
python -m compileall -q master/app agent/app installer
cd frontend && npm ci && npm run typecheck && npm run build
```

Operational deployment steps are in [DEPLOYMENT.md](DEPLOYMENT.md). Architecture and threat controls are in [ARCHITECTURE.md](ARCHITECTURE.md) and [SECURITY.md](SECURITY.md).

<!-- frontend-static-ci-verification -->
