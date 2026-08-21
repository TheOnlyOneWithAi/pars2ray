# Pars2Ray Production Audit — 2026-08-21

## Scope

Full production review baseline: backend, agent, installer, frontend, Docker/Compose, authentication, database/migrations, security, CI and E2E behavior.

## Startup/deployment

- Keep `master` as the single migration owner.
- Do not run `Base.metadata.create_all()` as an application startup migration path when Alembic is authoritative.
- Worker startup must wait for the migrated master/schema readiness.
- PostgreSQL connection attempts must have bounded timeouts.
- Health verification must retry and print actionable master/database/Redis diagnostics on failure.
- Container health checks must tolerate normal initialization without masking persistent failures.

## Production invariants

1. Services bind to `0.0.0.0` inside containers.
2. Runtime ports must be configurable by deployment environment where required.
3. Secrets must never be logged or committed.
4. Authentication failures must not reveal whether an account exists.
5. Database schema changes must be performed through versioned migrations.
6. Worker and API startup must fail clearly rather than hanging indefinitely.
7. Health endpoints must reflect dependency readiness, not merely process existence.
8. Installer failures must include enough diagnostics to identify the failing dependency.

## Verification

The previous startup hardening PR passed the repository CI/E2E suite before merge. This branch records the production-audit baseline and is intentionally kept separate from `main` until any additional code changes are independently validated.

## Follow-up checks

- Validate deployment against a real remote server using the exact installer path.
- Exercise fresh database initialization and upgrade-from-existing-database paths.
- Exercise authentication, token expiration/revocation, node CRUD, agent registration and reconnect behavior.
- Validate frontend build/runtime API configuration and error handling.
- Run security/static analysis and full E2E after every functional change.
