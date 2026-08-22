# Verification gates

Pars2Ray keeps the verification surface explicit so every refactor can be checked before release.

## CI gates

The `Pars2Ray CI` workflow currently validates:

- Python dependency consistency with `pip check`.
- Python bytecode compilation for `master`, `agent`, `installer`, and repository scripts.
- Ruff linting across all Python application and installer code.
- Master, agent, and repository-level pytest suites.
- Native installer compilation/imports, shell syntax, required files, and APT mirror policy.
- Frontend dependency installation, TypeScript typechecking, and production build.
- Direct dependency pin consistency.
- Python dependency vulnerability audits with `pip-audit`.
- Bandit static security scanning.
- Frontend production dependency auditing with `npm audit`.

## Engineering rules

1. Keep API validation at the boundary and return stable error identifiers.
2. Keep database models free of unnecessary bidirectional relationships unless a query path needs them.
3. Keep secrets encrypted at rest and out of public response schemas.
4. Keep installer logic deterministic and usable without Docker.
5. Keep frontend typechecking and production builds in CI rather than relying on local development builds.
6. Prefer small, testable service functions over large route handlers.
7. Treat a green CI run as the merge gate; documentation must never claim a check passed unless CI or a reproducible local run actually proves it.

## Architecture target

Pars2Ray is intentionally not a source-level clone of 3X-UI. The target is comparable engineering discipline: clear module boundaries, explicit validation, deterministic configuration generation, secure credential handling, testable services, reproducible installation, and a CI pipeline that catches regressions early.

The reference 3X-UI architecture separates HTTP/controller concerns from services and uses a clear database → configuration → Xray runtime pipeline. Pars2Ray follows the same principle across its Python master, node agent, installer, and frontend layers.
