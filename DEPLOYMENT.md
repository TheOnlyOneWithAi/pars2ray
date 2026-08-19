# Deployment

## Compose deployment

For a fresh Ubuntu/Debian host, the complete installer is available as one command:

```bash
curl -fsSL https://raw.githubusercontent.com/parsahoseini549-star/pars2ray/main/deploy/install.sh | sudo bash
```

Review the installer before execution when applying organizational supply-chain policy. It is idempotent for a clean Pars2Ray checkout and preserves an existing `.env` by creating a timestamped backup.

1. Copy `.env.example` to `.env`.
2. Generate secrets with `openssl rand -hex 32` and set `JWT_SECRET` and `MASTER_SECRET`.
3. Set a strong `POSTGRES_PASSWORD` and `ADMIN_PASSWORD`.
4. Set `TRUSTED_HOSTS` to the public hostnames and `CORS_ORIGINS` to the console origins.
5. Start with `docker compose --env-file .env -f deploy/docker-compose.yml up -d --build`.
6. Verify `curl http://127.0.0.1:8000/health` and inspect `/docs`.

The image startup runs `alembic upgrade head` before Uvicorn. The worker runs the same idempotent migration check and performs token cleanup. PostgreSQL and Redis are not exposed on host ports.

## Backups

```bash
./deploy/scripts/backup.sh
```

The script creates a timestamped compressed PostgreSQL dump and Redis snapshot directory. Keep encrypted off-host copies and regularly test restore procedures.

## Bootstrap nodes

Fill `PANEL_*` and every node entry with a non-empty `*_IP`. The installer uploads the repository, installs Docker on the Master, installs the agent and systemd service on each node, generates per-node tokens, and registers them. Empty IP entries are ignored. After bootstrap, remove SSH passwords from the operator workstation and restrict agent port 9100 to the Master IP.

## Production checklist

- Put the Master behind TLS and a reverse proxy.
- Set `TRUSTED_HOSTS` and CORS explicitly.
- Rotate `MASTER_SECRET` only with a planned re-encryption migration.
- Use database backups and log aggregation outside the container.
- Keep Xray/sing-box packages pinned and installed through your approved supply chain.
