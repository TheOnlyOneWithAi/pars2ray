from __future__ import annotations

import json

import httpx

from app.core.config import settings

SYSTEM_INSTRUCTIONS = """You are the senior decision engine for a production proxy/filter-routing operator. Think like a veteran filter seller and network optimizer: evidence first, conservative with production, aggressively test only bounded candidates. Optimize practical customer outcome: availability and stability first, then latency/jitter/loss, then throughput, while avoiding needless churn. Never invent measurements, credentials, IPs, users, passwords, tunnel configs, or facts. You only receive sanitized telemetry. Prefer KEEP when evidence is weak. Use TEST for promising but unproven candidates, CANARY for validated improvements, SWITCH only for a clearly superior validated candidate, and ROLLBACK only when the current route is demonstrably degraded. You never execute production changes yourself; local validator and policy gate are authoritative. Return only the schema."""

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


def safe_context(context: dict) -> dict:
    route = context.get("current_route") if isinstance(context.get("current_route"), dict) else {}
    route_fields = ("route_id", "route_hash", "core", "protocol", "transport", "score", "status")
    safe_route = {key: route[key] for key in route_fields if key in route}
    candidates: list[dict] = []
    for candidate in context.get("candidates", [])[:20]:
        if not isinstance(candidate, dict):
            continue
        candidate_fields = ("candidate_id", "core", "protocol", "transport", "score", "latency_ms", "jitter_ms", "packet_loss_percent", "throughput_mbps", "stability_percent", "node_count")
        candidates.append({key: candidate[key] for key in candidate_fields if key in candidate})
    return {"current_route": safe_route, "current_score": context.get("current_score"), "previous_score": context.get("previous_score"), "trigger": str(context.get("trigger", ""))[:120], "candidates": candidates}


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
        return {"action": "KEEP", "candidate_id": None, "confidence": 1.0, "reason": "AI disabled or not configured; local policy retained the safe configuration."}, {}
    payload = {"model": settings.openai_model, "store": False, "reasoning": {"effort": "low"}, "max_output_tokens": settings.ai_max_output_tokens, "prompt_cache_key": settings.ai_prompt_cache_key, "instructions": SYSTEM_INSTRUCTIONS, "input": [{"role": "user", "content": json.dumps(safe_context(context), separators=(",", ":"), ensure_ascii=False)}], "text": {"format": {"type": "json_schema", "name": "optimizer_decision", "strict": True, "schema": SCHEMA}}}
    async with httpx.AsyncClient(timeout=settings.openai_request_timeout_seconds, headers={"Content-Type": "application/json", "User-Agent": "Pars2Ray-Optimizer/2.3"}) as client:
        response = await client.post(settings.openai_base_url.rstrip("/") + "/responses", headers={"Authorization": f"Bearer {settings.openai_api_key}"}, json=payload)
        response.raise_for_status()
        data = response.json()
    return _extract_output(data), data.get("usage", {})
