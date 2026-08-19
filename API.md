# API

FastAPI generates the authoritative OpenAPI 3.1 contract at `/openapi.json`; interactive views are `/docs` and `/redoc`.

## Authentication

`POST /api/v1/auth/login` returns a short-lived access token and a refresh token. Send `Authorization: Bearer <access_token>` or `X-API-Key: <api-key>`. Refresh tokens are one-time rotated by `POST /api/v1/auth/refresh`.

## Resource groups

| Group | Endpoints |
|---|---|
| Auth | `/api/v1/auth/*`, `/api/v1/api-keys` |
| Nodes | `/api/v1/nodes`, registration, benchmark, restart, drain, rollback |
| Routes | `/api/v1/routes` and activation |
| Experiments | `/api/v1/experiments` and promotion |
| Optimizer | `/api/v1/optimizer/decide`, decisions, bounded candidates |
| Users | `/api/v1/users` |
| Subscriptions/Billing | `/api/v1/subscriptions`, `/api/v1/plans` |
| System | dashboard, health, audit logs, settings, national mode, research |

## Node registration

Bootstrap sends `X-Master-Secret` once to `POST /api/v1/nodes/register`. The Master stores only the hash and encrypted form of the agent token. Runtime calls use `X-Agent-Token` between Master and Agent.

## OpenAI decision contract

The internal AI gateway sends a Responses API request with `store=false` and `text.format.type=json_schema`. The returned object is constrained to `KEEP`, `TEST`, `CANARY`, `SWITCH`, or `ROLLBACK` and is always passed through the local validator.
