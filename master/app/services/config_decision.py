from __future__ import annotations

import json
from typing import Any

from app.services.openai_optimizer import _runtime_config

ALLOWED_PROTOCOLS = {"vless", "vmess", "shadowsocks"}
ALLOWED_TRANSPORTS = {"tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"}
ALLOWED_SECURITY = {"none", "tls", "reality"}
REALITY_TRANSPORTS = {"tcp", "xhttp", "grpc"}


def validate_decision(value: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    out = dict(fallback)
    for key in ("protocol", "transport", "security", "sni", "host", "path", "service_name", "flow", "fingerprint", "public_key", "short_id"):
        if key in value and value[key] not in (None, ""):
            out[key] = str(value[key])
    if isinstance(value.get("port"), int) and 1 <= value["port"] <= 65535:
        out["port"] = value["port"]
    if out.get("protocol") not in ALLOWED_PROTOCOLS:
        out["protocol"] = fallback["protocol"]
    if out.get("transport") not in ALLOWED_TRANSPORTS:
        out["transport"] = fallback["transport"]
    if out.get("security") not in ALLOWED_SECURITY:
        out["security"] = fallback["security"]
    if out["security"] == "reality" and out["transport"] not in REALITY_TRANSPORTS:
        out["transport"] = "tcp"
    # REALITY client links are unusable without the server-provided public key and short id.
    if out["security"] == "reality" and (not out.get("public_key") or not out.get("short_id") or not out.get("sni") or not out.get("fingerprint")):
        out = dict(fallback)
    if out["protocol"] != "vless":
        out["flow"] = None
    if out["security"] == "none":
        out["sni"] = None
        out["fingerprint"] = None
        out["public_key"] = None
        out["short_id"] = None
    if out["security"] != "reality":
        out["public_key"] = None
        out["short_id"] = None
    if out["transport"] not in {"websocket", "httpupgrade", "xhttp"}:
        out["host"] = None
        out["path"] = "/"
    if out["transport"] != "grpc":
        out["service_name"] = None
    return out


async def decide_config(snapshot: dict[str, Any], fallback: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    enabled, model, api_key = _runtime_config()
    if not enabled:
        return dict(fallback), {"enabled": False, "reason": "ai_disabled"}

    system = (
        "You are Pars2Ray's configuration decision engine. Return JSON only. "
        "Choose the safest compatible configuration from the supplied snapshot. "
        "Never invent IPs, keys, credentials, certificates, or measurements. "
        "The local validator is authoritative. REALITY is only valid with tcp, xhttp, or grpc. "
        "Use REALITY only when public_key, short_id, sni and fingerprint already exist in the snapshot. "
        "Otherwise keep the supplied fallback rather than inventing security material."
    )
    schema = {"type": "object", "properties": {
        "protocol": {"type": "string"}, "port": {"type": "integer"}, "transport": {"type": "string"}, "security": {"type": "string"},
        "sni": {"type": ["string", "null"]}, "host": {"type": ["string", "null"]}, "path": {"type": ["string", "null"]}, "service_name": {"type": ["string", "null"]},
        "flow": {"type": ["string", "null"]}, "fingerprint": {"type": ["string", "null"]}, "public_key": {"type": ["string", "null"]}, "short_id": {"type": ["string", "null"]}},
        "required": ["protocol", "port", "transport", "security"], "additionalProperties": False}
    import httpx
    from app.core.config import settings
    payload = {"model": model, "store": False, "reasoning": {"effort": "low"}, "max_output_tokens": min(settings.ai_max_output_tokens, 220), "prompt_cache_key": settings.ai_prompt_cache_key + ":config", "instructions": system, "input": [{"role": "user", "content": json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False)}], "text": {"format": {"type": "json_schema", "name": "config_decision", "strict": True, "schema": schema}}}
    try:
        async with httpx.AsyncClient(timeout=settings.openai_request_timeout_seconds) as client:
            response = await client.post(settings.openai_base_url.rstrip("/") + "/responses", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=payload)
            response.raise_for_status()
            data = response.json()
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return validate_decision(json.loads(content["text"]), fallback), {"enabled": True, "model": model, "usage": data.get("usage", {})}
    except Exception as exc:
        return dict(fallback), {"enabled": True, "fallback": True, "reason": type(exc).__name__}
    return dict(fallback), {"enabled": True, "fallback": True, "reason": "empty_ai_output"}
