from __future__ import annotations

import asyncio
import json
import shlex

import httpx

from app.core.config import settings
from app.core.security import decrypt_secret
from app.services.ssh_provision import _client, _exec, decode_config


async def _ssh_request(node, method: str, path: str, json_data=None):
    if not node.ssh_config_enc:
        raise RuntimeError("node_agent_http_and_ssh_unavailable")
    token = decrypt_secret(node.agent_token_enc)
    config = decode_config(node.ssh_config_enc)
    payload = json.dumps(json_data or {}, separators=(",", ":"))
    remote = (
        "export X_AGENT_TOKEN=%s; printf '%%s' %s | curl -fsS --connect-timeout 5 --max-time 30 "
        "-X %s -H 'X-Agent-Token: '$X_AGENT_TOKEN -H 'Content-Type: application/json' --data-binary @- %s"
    ) % (shlex.quote(token), shlex.quote(payload), shlex.quote(method), shlex.quote(f"http://127.0.0.1:9100{path}"))

    def run():
        client = _client(config)
        try:
            _, stdout, stderr = _exec(client, remote, timeout=35)
            code = stdout.channel.recv_exit_status()
            body = stdout.read().decode("utf-8", "replace")
            if code != 0:
                detail = stderr.read().decode("utf-8", "replace")[-1000:]
                raise RuntimeError(f"node_agent_ssh_request_failed:{detail or code}")
            return json.loads(body)
        finally:
            client.close()

    return await asyncio.to_thread(run)


async def request(node, method: str, path: str, json_data=None):
    token = decrypt_secret(node.agent_token_enc)
    headers = {"X-Agent-Token": token}
    try:
        async with httpx.AsyncClient(timeout=settings.agent_request_timeout_seconds, follow_redirects=False) as client:
            response = await client.request(method, node.endpoint.rstrip("/") + path, headers=headers, json=json_data)
            response.raise_for_status()
            return response.json()
    except (httpx.TransportError, OSError, TimeoutError):
        try:
            return await _ssh_request(node, method, path, json_data)
        except Exception as ssh_error:
            raise RuntimeError("node_agent_unreachable") from ssh_error


async def command(node, name: str, payload: dict | None = None):
    return await request(node, "POST", "/command", {"command": name, "payload": payload or {}})


async def health(node):
    return await command(node, "GET_STATUS")


async def metrics(node):
    return await command(node, "GET_METRICS")


async def core_status(node):
    return await command(node, "GET_CORE_STATUS")


async def config(node):
    return await command(node, "GET_CONFIG")


async def benchmark(node, payload):
    return await command(node, "RUN_BENCHMARK", payload)


async def apply_config(node, payload):
    return await command(node, "APPLY_CONFIG", payload)


async def update_existing_inbounds(node, updates):
    return await command(node, "UPDATE_EXISTING_INBOUNDS", {"updates": updates})


async def rollback(node, operation_id: str | None = None):
    payload = {"operation_id": operation_id} if operation_id else {}
    return await command(node, "ROLLBACK", payload)


async def restart(node):
    return await command(node, "RESTART_SERVICE")


async def start(node):
    return await command(node, "START_SERVICE")


async def stop(node):
    return await command(node, "STOP_SERVICE")


async def version(node):
    return await command(node, "CORE_VERSION")


async def logs(node, lines: int = 200):
    return await command(node, "CORE_LOGS", {"lines": lines})


async def update_core(node):
    return await command(node, "UPDATE_CORE")


async def firewall_status(node):
    return await command(node, "FIREWALL_STATUS")
