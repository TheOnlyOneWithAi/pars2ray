## Summary

Describe the change and the operational reason for it.

## Verification

- [ ] `PYTHONPATH=master pytest -q tests`
- [ ] `python -m compileall -q master/app agent/app installer migrations`
- [ ] `cd frontend && npm run typecheck && npm run build`
- [ ] Docker Compose configuration checked

## Safety review

- [ ] No credentials, raw tunnel configuration, or sensitive telemetry is exposed.
- [ ] Node-agent commands remain allowlisted.
- [ ] AI cannot bypass local validation or directly change production.
- [ ] Migrations and rollback behavior were considered.
