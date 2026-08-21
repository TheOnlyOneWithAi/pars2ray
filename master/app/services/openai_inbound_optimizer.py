from __future__ import annotations

import json

import httpx

from app.core.config import settings
from app.services.openai_optimizer import _runtime_config

SYSTEM_INSTRUCTIONS = """You are Pars2Ray's senior proxy configuration optimizer. You are given only sanitized metadata for EXISTING Xray or sing-box inbounds. You must NEVER create an inbound, delete an inbound, change its tag, port, listen address, client credentials, UUIDs, passwords, public keys, or other secrets. Select protocol and transport only when supported by the active core. Return updates ONLY for existing inbound tags supplied in the input. Prefer KEEP when evidence is weak. The local validator is authoritative and will reject unsupported changes. Optimize availability and stability first, then latency/jitter/loss. Return only the JSON schema."""

SCHEMA = {
    "type": "object",
    "properties": {
        "updates": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "minLength": 1, "maxLength": 128},
                    "protocol": {"type": "string", "enum": ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"]},
                    "transport": {"type": "string", "enum": ["tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"]},
                    "reason": {"type": "string", "maxLength": 300},
                },
                "required": ["tag", "protocol", "transport", "reason"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string", "maxLength": 500},
    },
    "required": ["updates", "reason"],
    "additionalProperties": False,
}


def _extract(data: dict) -> dict:
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return json.loads(content["text"])
    raise ValueError("structured_output_missing")


async def suggest(core: str, inbounds: list[dict], telemetry: dict | None = None) -> tuple[dict, dict]:
    enabled, model, api_key = _runtime_config()
    if not enabled:
        raise RuntimeError("ai_not_configured")
    safe = []
    allowed = {"xray": ["vless", "vmess", "trojan", "shadowsocks"], "sing-box": ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"]}.get(core, [])
    for item in inbounds[:20]:
        safe.append({"tag": str(item.get("tag", "")), "protocol": str(item.get("protocol", "")), "transport": str(item.get("transport", "tcp")), "port": item.get("port"), "listen": item.get("listen", "")})
    payload = {
        "core": core,
        "allowed_protocols": allowed,
        "allowed_transports": ["tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"],
        "existing_inbounds": safe,
        "telemetry": telemetry or {},
    }
    body = {"model": model, "store": False, "reasoning": {"effort": "low"}, "max_output_tokens": settings.ai_max_output_tokens, "prompt_cache_key": settings.ai_prompt_cache_key, "instructions": SYSTEM_INSTRUCTIONS, "input": [{"role": "user", "content": json.dumps(payload, separators=(",", ":"), ensure_ascii=False)}], "text": {"format": {"type": "json_schema", "name": "inbound_optimizer", "strict": True, "schema": SCHEMA}}}
    async with httpx.AsyncClient(timeout=settings.openai_request_timeout_seconds, headers={"Content-Type": "application/json", "User-Agent": "Pars2Ray-Inbound-Optimizer/2.3"}) as client:
        response = await client.post(settings.openai_base_url.rstrip("/") + "/responses", headers={"Authorization": f"Bearer {api_key}"}, json=body)
        response.raise_for_status()
        data = response.json()
    return _extract(data), data.get("usage", {})
