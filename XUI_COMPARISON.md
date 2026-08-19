# Pars2Ray and X-UI / 3X-UI comparison

This review uses the public `MHSanaei/3x-ui` repository and its README, installer, backend, frontend, and documentation tree as the reference. It is a feature comparison and design review; Pars2Ray does not copy X-UI source code or assets.

Reference: [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui), reviewed against its `main` branch on 2026-08-19.

## Capability comparison

| Area | 3X-UI strength | Pars2Ray today | Decision |
|---|---|---|---|
| Core control | Direct Xray gRPC API, process lifecycle, hot diff and live reload | Secure Node Agent allowlist with config validation, rollback and restart | Adopt a safe Core Status command and keep config execution inside the agent |
| Client operations | Per-client quota, expiry, IP/device limits, online status | User, plan and subscription records with node assignment | Keep subscription secrets out of the browser; add operational usage and status views incrementally |
| Traffic | Per-inbound, client and outbound counters with reset controls | Persisted per-node RX/TX and metric history | Add server-side traffic breakdown by node and time range |
| Routing | Outbounds, WARP, custom routing, load balancing and chaining | Route records, node paths, protocol, transport, score and activation | Preserve AI gate/canary and add searchable route operations |
| Sharing | Share links, QR codes and multiple subscription formats | Secret-safe subscription records, no raw URI in API/UI | Do not expose full URIs, UUIDs, keys or raw subscription responses |
| Panel UX | Searchable inbounds/clients, live dashboard, dark/light themes, 13 locales | Responsive dark panel with English, Persian RTL and Russian | Add server-side filters, real Core status and keep the current clean UI |
| Delivery | Mature installer, CLI, Docker, SQLite/PostgreSQL options and Fail2ban integration | Docker Compose, PostgreSQL, Redis, migrations, backups and one-line installer | Keep the enterprise PostgreSQL architecture; document operational checks and hardening |
| API/docs | REST API, generated Swagger and route contract tests | FastAPI OpenAPI 3.1, `/docs`, `/redoc`, `/openapi.json` | Add contract coverage for every new operational endpoint |

## Implemented in this upgrade

- Search, status/protocol filters and bounded pagination are available on node, route, user and subscription list APIs.
- A fixed `GET_CORE_STATUS` agent command reports installed core, version, service state and active configuration metadata without allowing shell input.
- The Master exposes a node Core Status operation and a dashboard traffic breakdown aggregated from persisted samples.
- The panel can use the new operations without receiving route secrets or raw configuration payloads.
- The comparison and adoption decisions are documented here so future features are evaluated against Pars2Ray's security and Master/Agent boundaries.

## Deliberately not copied

The X-UI README advertises one-click share links, QR codes and subscription formats. Pars2Ray's privacy contract forbids returning full VLESS/VMess/Trojan/Shadowsocks/Hysteria2 URIs, UUIDs, passwords, private keys, subscription URLs or raw subscription responses to the panel browser. A future delivery service must issue short-lived, scoped links from a separate boundary and must never place those secrets in HTML, JavaScript state, analytics, logs or audit metadata.

Direct Xray gRPC management is also not placed in the Master. The Node Agent remains the only component allowed to interact with a local core, using fixed commands and validated configurations. This retains rollback and canary guarantees that a direct production switch from an AI decision would violate.

## Next safe increments

1. Add a typed inbound/client domain with encrypted-at-rest secrets and redacted API projections.
2. Add a separate subscription delivery service with expiring tokens, format adapters and rate limits.
3. Add optional WebSocket telemetry after token binding and connection authorization are specified.
4. Add fail2ban integration as an install-time hardening option with an explicit operator opt-out.
