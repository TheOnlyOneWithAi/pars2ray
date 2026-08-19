# API

FastAPI generates the authoritative OpenAPI 3.1 contract at `/openapi.json`; interactive views are `/docs` and `/redoc`.

## Authentication

`POST /api/v1/auth/login` returns a short-lived access token and a refresh token. Send `Authorization: Bearer <access_token>` or `X-API-Key: <api-key>`. Refresh tokens are one-time rotated by `POST /api/v1/auth/refresh`.

Create an API key with `POST /api/v1/api-keys` and a JSON body such as `{"name":"deploy","scopes":["read"],"expires_in_days":90}`. The raw key is returned once. Use `GET /api/v1/api-keys` to review redacted metadata and `DELETE /api/v1/api-keys/{id}` to revoke a key. Supported scopes are `read`, `write`, `admin`, and `*`; an empty scope list keeps the user's RBAC boundary without adding a scope restriction. Expired or revoked keys are rejected.

## Resource groups

| Group | Endpoints |
|---|---|
| Auth | `/api/v1/auth/*`, `/api/v1/api-keys` |
| Nodes | `/api/v1/nodes`, search/filter/limit, metric history, Core Status, registration, benchmark, restart, drain, rollback |
| Routes | `/api/v1/routes` and activation |
| Experiments | `/api/v1/experiments` and promotion |
| Optimizer | `/api/v1/optimizer/decide`, decisions, bounded candidates |
| Users | `/api/v1/users` |
| Subscriptions/Billing | `/api/v1/subscriptions`, `/api/v1/plans` |
| System | dashboard, traffic telemetry/breakdown, health, audit logs, settings, national mode, research |

## Control panel telemetry

`GET /api/v1/dashboard/telemetry?hours=24` returns persisted RX/TX samples aggregated into UTC hourly buckets. The range is bounded to 1–168 hours. `GET /api/v1/nodes/{node_key}/metrics?limit=60` returns measured latency, loss, throughput, stability, CPU, and memory history for a selected node. The limit is bounded to 1–500 rows.

`GET /api/v1/dashboard/traffic-breakdown?hours=24` returns redacted per-node RX/TX totals from persisted samples. `GET /api/v1/nodes/{node_key}/core-status` asks the Node Agent for the installed core, version, fixed service state, and active-config metadata. It never returns the configuration body or credentials.

## Node registration

Bootstrap sends `X-Master-Secret` once to `POST /api/v1/nodes/register`. The Master stores only the hash and encrypted form of the agent token. Runtime calls use `X-Agent-Token` between Master and Agent.

## OpenAI decision contract

The internal AI gateway sends a Responses API request with `store=false` and `text.format.type=json_schema`. The returned object is constrained to `KEEP`, `TEST`, `CANARY`, `SWITCH`, or `ROLLBACK` and is always passed through the local validator.

Requests are gated locally before the provider call. A stable prompt-cache key is reused, variable telemetry is bounded and placed after the stable instructions, and no call is made when there is no candidate set to evaluate.
