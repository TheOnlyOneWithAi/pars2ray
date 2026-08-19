# Contributing

## Workflow

Use small focused commits. Add a deterministic backend test for policy or service changes. Keep API contracts backward compatible within `/api/v1`; breaking changes require a new version or migration note.

## Checks

```bash
PYTHONPATH=master pytest -q tests
python -m compileall -q master/app agent/app installer
cd frontend && npm run typecheck && npm run build
```

Do not add arbitrary shell execution, raw credentials to telemetry, or UI copy that bypasses local gate/validator rules. Keep node-agent dependencies minimal and document any new command in the allowlist and API contract.
