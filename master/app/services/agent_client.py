from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.security import decrypt_secret


async def request(node, method: str, path: str, json_data=None):
    token = decrypt_secret(node.agent_token_enc)
    headers = {"X-Agent-Token": token}
    async with httpx.AsyncClient(timeout=settings.agent_request_timeout_seconds, follow_redirects=False) as client:
        response = await client.request(method, node.endpoint.rstrip("/") + path, headers=headers, json=json_data)
        response.raise_for_status()
        return response.json()


async def command(node, name: str, payload: dict | None = None):
    return await request(node, "POST", "/command", {"command": name, "payload": payload or {}})


async def health(node):
    return await command(node, "GET_STATUS")


async def metrics(node):
    return await command(node, "GET_METRICS")


async def benchmark(node, payload):
    return await command(node, "RUN_BENCHMARK", payload)


async def apply_config(node, payload):
    return await command(node, "APPLY_CONFIG", payload)


async def rollback(node):
    return await command(node, "ROLLBACK")


async def restart(node):
    return await command(node, "RESTART_SERVICE")
