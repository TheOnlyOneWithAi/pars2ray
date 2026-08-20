# Pars2Ray — Top 3 Intelligence Features

This document defines the three highest-priority capabilities for Pars2Ray. The product should behave like a network operating system and an operator's NOC, not just a configuration UI.

## P0-1 — Network Intelligence Engine

**Goal:** turn raw node telemetry into safe, explainable routing decisions.

```text
Telemetry -> Health Engine -> Scoring Engine -> Policy / Safety Gate
          -> AI Advisor (optional) -> Experiment Controller -> Outcome / Memory
```

Rules:
- Availability and stability are weighted above raw throughput.
- Latency, jitter and packet loss are evaluated together.
- AI is advisory; deterministic validation and policy gates remain authoritative.
- AI receives sanitized telemetry only — never credentials, API keys, passwords or full tunnel configuration.
- If evidence is weak, default to `KEEP`.
- Every automated decision has a machine-readable reason and confidence value.

Decision contract:

```json
{"action":"KEEP | TEST | CANARY | SWITCH | ROLLBACK","candidate_id":"string | null","confidence":0.0,"reason":"string"}
```

## P0-2 — Golden Configs + Operational Memory

**Goal:** make Pars2Ray learn from its own production history instead of asking an LLM to reason from scratch every time.

### Route DNA

Each validated route/configuration gets a stable fingerprint containing only non-secret characteristics:

- core / protocol / transport
- configuration hash and node identity
- latency / jitter / packet loss / throughput
- stability and availability
- validation count and success rate
- historical incident outcomes

A configuration becomes `GOLDEN` only after repeated successful validation. Golden configs are ranked by context, not globally.

### Memory model

```text
Situation -> Candidate -> Decision -> Outcome
```

Before an AI call, retrieve relevant historical outcomes and golden configurations. This reduces token usage and makes the AI behave more like an experienced operator with a long memory.

**Privacy:** never persist raw credentials or secrets in operational memory. Store hashes, measurements and safe metadata only.

## P0-3 — Experiment Lab: Test → Canary → Promote → Rollback

**Goal:** replace risky direct production changes with bounded experiments.

```text
PROPOSED -> TESTING -> CANARY -> VALIDATED -> PROMOTED
               |          |
             FAILED   ROLLED_BACK
```

A candidate can be promoted only when:
1. minimum sample count is reached;
2. health checks pass;
3. composite score improves by the configured threshold;
4. no critical regression is detected;
5. the deterministic policy gate approves the change.

Rollback is automatic when a promoted candidate breaches configured degradation thresholds.

### Operator autonomy

- **Conservative:** recommend only.
- **Assisted:** test/canary automatically; production promotion requires approval.
- **Autonomous:** allow only policy-bounded promotion and automatic rollback.

## Why these three come first

1. **Network Intelligence Engine** creates the decision layer.
2. **Golden Configs + Memory** gives it durable operational experience and lowers AI cost.
3. **Experiment Lab** turns decisions into safe, measurable production changes.

Together they form the Pars2Ray differentiator:

> Observe → remember → reason → experiment → validate → learn.

The UI, Telegram NOC, prediction, network map and Copilot should consume these primitives rather than becoming independent feature silos.
