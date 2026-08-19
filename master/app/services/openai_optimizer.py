from __future__ import annotations

import json

import httpx

from app.core.config import settings

SYSTEM_INSTRUCTIONS = """You are a conservative network optimization decision service. Use only supplied telemetry. Never invent measurements or credentials. Production changes are never executed by you. Prefer KEEP; then TEST; then CANARY. A SWITCH is valid only when a candidate is verified, has materially better score, and passes local policy. Return only the schema."""

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["KEEP", "TEST", "CANARY", "SWITCH", "ROLLBACK"]},
        "candidate_id": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "maxLength": 500},
    },
    "required": ["action", "candidate_id", "confidence", "reason"],
    "additionalProperties": False,
}


def _extract_output(data: dict) -> dict:
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return json.loads(content["text"])
    raise ValueError("structured_output_missing")


async def analyze(context: dict) -> tuple[dict, dict]:
    if not settings.ai_enabled or not settings.openai_api_key:
        return {"action": "KEEP", "candidate_id": None, "confidence": 1.0, "reason": "AI unavailable; local policy retained the safe configuration."}, {}
    payload = {
        "model": settings.openai_model,
        "store": False,
        "reasoning": {"effort": "low"},
        "max_output_tokens": settings.ai_max_output_tokens,
        "prompt_cache_key": settings.ai_prompt_cache_key,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": [{"role": "user", "content": json.dumps(context, separators=(",", ":"), ensure_ascii=False)}],
        "text": {"format": {"type": "json_schema", "name": "optimizer_decision", "strict": True, "schema": SCHEMA}},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(settings.openai_base_url.rstrip("/") + "/responses", headers={"Authorization": f"Bearer {settings.openai_api_key}"}, json=payload)
        response.raise_for_status()
        data = response.json()
    return _extract_output(data), data.get("usage", {})
