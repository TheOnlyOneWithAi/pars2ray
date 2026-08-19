# Security

## Controls

- Argon2id password hashing with no plaintext password persistence.
- Short-lived JWT access tokens, refresh rotation, revocation, and hashed refresh storage.
- RBAC roles: Super Admin, Admin, Operator, Reseller, User.
- Hashed API keys; raw key is returned only at creation.
- API keys can expire and are restricted by `read`, `write`, `admin`, or `*` scopes before role checks.
- Fernet encryption for agent tokens and route configurations using `MASTER_SECRET`.
- In-memory rate limiter in the API process, with Redis available for production coordination.
- Audit events for authentication, node lifecycle, route changes, optimizer decisions, and user changes.
- Security headers, trusted-host validation, restrictive CORS, no-store API responses.
- No raw node secrets in list responses, frontend state, or UI tables.
- Experiment, subscription, audit, metric, plan, and research list endpoints use explicit response projections instead of serializing ORM objects wholesale.
- Node agent has no arbitrary shell execution and no remote file upload endpoint.

## AI data handling

Only normalized telemetry, route metadata, and bounded candidates are sent to the configured AI provider. Credentials and raw tunnel configuration are not included in the optimizer context. Requests set `store=false`, use strict structured outputs, reuse a stable prompt-cache key, and use low reasoning/output limits. If the provider is unavailable, the local policy retains the active route or searches bounded templates.

## Operations

Run dependency scanning in CI, patch base images, restrict firewall ingress, and monitor audit logs. Treat `.env`, database dumps, and agent state as secrets. Do not commit them.
