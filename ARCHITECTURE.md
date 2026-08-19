# Architecture

## Runtime topology

```text
Browser ──HTTPS──> Master API ──SQL──> PostgreSQL
                         │              └─ persistent data
                         ├── Redis (rate-limit/worker coordination)
                         ├── background scheduler/worker
                         └── authenticated HTTPS/agent token ──> Node Agent
                                                                  ├─ telemetry
                                                                  └─ Xray or sing-box adapter
```

The Master owns identity, policy, experiment memory, route state, subscriptions, billing metadata, and audit records. Node Agents are stateless control adapters with local rollback state. Agents do not ship a frontend, database, Swagger UI, arbitrary command endpoint, or SSH credentials.

## Decision pipeline

1. Agents expose heartbeat, metrics, health, and bounded benchmark results.
2. The Master stores metrics and experiment measurements.
3. A deterministic gate decides whether an AI call is justified.
4. If justified, the Responses API returns a strict decision object.
5. The local validator checks protocol/core/transport, score improvement, and config shape.
6. Only a canary workflow may proceed to production; the AI response itself never calls an agent.
7. Verified and golden experiment memory supports national-mode fallback.

## Boundaries

The API is organized under `/api/v1`. The database layer uses SQLAlchemy 2 and Alembic. The UI is a separate Vite build copied into `master/app/static` for a single deployable master image. Compose keeps PostgreSQL and Redis private to the internal network.
