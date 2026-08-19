# Pars2Ray Enterprise

Pars2Ray is a production-oriented network orchestration control plane with one FastAPI master, PostgreSQL persistence, Redis service, background worker, React/TypeScript console, and authenticated lightweight node agents.

## Repository

```text
master/       FastAPI control plane, domain services, persistence, worker
agent/        node-only agent; no UI or database
frontend/     React + TypeScript enterprise console
migrations/   Alembic migration environment and initial schema
installer/    SSH bootstrap only; credentials are not used by runtime agents
deploy/       Docker Compose, startup and backup scripts
tests/        deterministic backend tests
```

## Quick start

```bash
cp .env.example .env
# replace all replace-with-* values
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

The master serves the console at `http://localhost:8000/`. API documentation is at `/docs`, `/redoc`, and `/openapi.json`. The initial Super Admin is created from `ADMIN_USER`, `ADMIN_PASSWORD`, and `ADMIN_EMAIL` on first startup.

For remote bootstrap, fill `PANEL_*` and any non-empty node entries such as `DE1_IP`, `DE2_IP`, `NL1_IP`, then run `python installer/bootstrap.py`. SSH is used only for installation and systemd setup; subsequent master/agent traffic uses the generated agent identity.

## Design guarantees

- Access JWTs are short-lived; refresh tokens are rotated and stored hashed.
- Passwords use Argon2id. Secrets are encrypted at rest with a key derived from `MASTER_SECRET`.
- Agent commands are an explicit allowlist: `GET_STATUS`, `GET_METRICS`, `RUN_BENCHMARK`, `APPLY_CONFIG`, `ROLLBACK`, `RESTART_SERVICE`.
- No arbitrary shell endpoint exists. Core execution is restricted to known Xray/sing-box validation and restart commands.
- Route configuration and node tokens are never returned by normal API list responses.
- Optimizer transitions pass local gate and validator checks; AI cannot directly change production.
- Without OpenAI access, experiment memory, golden configurations, local rules, and bounded fallback candidates continue to work.

## AI integration

The optimizer uses the OpenAI Responses API with `store=false`, low reasoning effort, a stable prompt cache key, and strict JSON Schema output through `text.format`. See [API.md](API.md) and [SECURITY.md](SECURITY.md).

## Verification

```bash
PYTHONPATH=master pytest -q tests
python -m compileall -q master/app agent/app installer
cd frontend && npm install && npm run typecheck && npm run build
```

Operational deployment steps are in [DEPLOYMENT.md](DEPLOYMENT.md). Architecture and threat controls are in [ARCHITECTURE.md](ARCHITECTURE.md) and [SECURITY.md](SECURITY.md).
