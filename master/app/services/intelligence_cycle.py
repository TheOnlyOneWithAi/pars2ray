from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.config import settings
from app.services.experiment_lab import ExperimentPolicy
from app.services.golden_memory import golden_candidates
from app.services.network_intelligence import build_intelligence_snapshot
from app.services.openai_optimizer import analyze


@dataclass(frozen=True)
class CycleDecision:
    action: str
    candidate_id: str | None
    reason: str


class IntelligenceCycle:
    """Bounded orchestration: evidence -> memory -> optional AI -> local safety decision."""

    def __init__(self) -> None:
        self.policy = ExperimentPolicy(min_improvement=settings.ai_switch_min_improvement, required_wins=settings.ai_required_wins)

    async def run_once(self) -> CycleDecision:
        snapshot = build_intelligence_snapshot()
        if not snapshot.get("current_route"):
            return CycleDecision("KEEP", None, "No active route is available.")
        candidates = snapshot.get("candidates", [])
        if not candidates:
            return CycleDecision("KEEP", None, "No measured candidates are available; skipped AI and experiments.")

        proven = {str(item["route_id"]) for item in golden_candidates(limit=20)}
        ordered = sorted(candidates, key=lambda item: (str(item.get("candidate_id")) in proven, float(item.get("score") or 0)), reverse=True)
        fallback = ordered[0]
        ai_decision, _usage = await analyze({**snapshot, "candidates": ordered[: settings.national_max_candidates_per_round]})
        action = str(ai_decision.get("action", "KEEP"))
        candidate_id = ai_decision.get("candidate_id") or fallback.get("candidate_id")
        # AI is advisory. Production promotion is never authorized by the LLM.
        if action == "SWITCH":
            action = "CANARY"
        if action not in {"KEEP", "TEST", "CANARY", "ROLLBACK"}:
            action = "KEEP"
        return CycleDecision(action, candidate_id, str(ai_decision.get("reason", "Local safety policy retained control.")))


async def run_intelligence_cycle() -> CycleDecision:
    return await IntelligenceCycle().run_once()


def run_intelligence_cycle_sync() -> CycleDecision:
    return asyncio.run(run_intelligence_cycle())
