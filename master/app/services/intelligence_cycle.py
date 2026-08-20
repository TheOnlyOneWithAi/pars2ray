from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

from app.core.config import settings
from app.services.experiment_lab import ExperimentPolicy
from app.services.network_intelligence import build_intelligence_snapshot
from app.services.openai_optimizer import analyze


@dataclass(frozen=True)
class CycleDecision:
    action: str
    candidate_id: str | None
    reason: str


class IntelligenceCycle:
    """Bounded orchestration: evidence -> optional AI advice -> deterministic local safety decision."""

    def __init__(self) -> None:
        self.policy = ExperimentPolicy(min_improvement=settings.ai_switch_min_improvement, required_wins=settings.ai_required_wins)

    @staticmethod
    def _ordered_candidates(candidates: list[dict]) -> list[dict]:
        valid: list[dict] = []
        for item in candidates:
            if not isinstance(item, dict) or not item.get("candidate_id"):
                continue
            try:
                score = float(item.get("score", 0))
            except (TypeError, ValueError):
                continue
            if math.isfinite(score):
                valid.append(item)
        return sorted(valid, key=lambda item: float(item.get("score", 0)), reverse=True)

    async def run_once(self) -> CycleDecision:
        snapshot = build_intelligence_snapshot()
        if not isinstance(snapshot, dict) or not snapshot.get("current_route"):
            return CycleDecision("KEEP", None, "No active route is available.")

        candidates = self._ordered_candidates(snapshot.get("candidates", []))
        if not candidates:
            return CycleDecision("KEEP", None, "No measured candidates are available; skipped AI and experiments.")

        fallback = candidates[0]
        fallback_id = str(fallback["candidate_id"])
        current_score = snapshot.get("current_score", snapshot["current_route"].get("score", 0))
        try:
            current_score = float(current_score)
        except (TypeError, ValueError):
            return CycleDecision("KEEP", None, "Invalid current score; local safety policy refused a decision.")
        if not math.isfinite(current_score):
            return CycleDecision("KEEP", None, "Invalid current score; local safety policy refused a decision.")

        # AI is strictly optional: disabled/missing key means local-only operation.
        if not settings.ai_enabled or not settings.openai_api_key:
            return CycleDecision("TEST", fallback_id, "AI is disabled; local policy selected the best measured candidate for testing.")

        try:
            ai_decision, _usage = await analyze({**snapshot, "candidates": candidates[: max(1, int(settings.national_max_candidates_per_round))]})
        except Exception:
            return CycleDecision("TEST", fallback_id, "AI analysis failed; local policy selected the best measured candidate.")

        if not isinstance(ai_decision, dict):
            return CycleDecision("TEST", fallback_id, "AI returned an invalid decision; local policy retained control.")

        requested_action = str(ai_decision.get("action", "KEEP")).upper()
        candidate_id = ai_decision.get("candidate_id")
        by_id = {str(item["candidate_id"]): item for item in candidates}
        selected = by_id.get(str(candidate_id)) if candidate_id is not None else fallback
        if selected is None:
            return CycleDecision("KEEP", None, "AI selected an unknown candidate; local policy rejected the decision.")

        selected_id = str(selected["candidate_id"])
        try:
            candidate_score = float(selected.get("score", 0))
        except (TypeError, ValueError):
            return CycleDecision("KEEP", None, "AI selected a candidate with an invalid score; local policy rejected it.")
        if not math.isfinite(candidate_score):
            return CycleDecision("KEEP", None, "AI selected a candidate with an invalid score; local policy rejected it.")

        if requested_action in {"SWITCH", "CANARY", "TEST"}:
            if candidate_score <= current_score:
                return CycleDecision("KEEP", selected_id, "Candidate is not measurably better than the current route; local policy kept the current route.")
            if requested_action == "SWITCH":
                requested_action = "CANARY"
            if requested_action == "CANARY" and candidate_score - current_score < self.policy.min_improvement:
                return CycleDecision("TEST", selected_id, "Candidate improved the score but has not cleared the local promotion threshold.")
            return CycleDecision(requested_action, selected_id, str(ai_decision.get("reason", "Candidate passed the local pre-check."))[:500])

        if requested_action == "ROLLBACK":
            return CycleDecision("ROLLBACK", None, str(ai_decision.get("reason", "AI requested rollback; production mutation remains behind local gates."))[:500])

        return CycleDecision("KEEP", None, str(ai_decision.get("reason", "Local safety policy retained control."))[:500])


async def run_intelligence_cycle() -> CycleDecision:
    return await IntelligenceCycle().run_once()


def run_intelligence_cycle_sync() -> CycleDecision:
    return asyncio.run(run_intelligence_cycle())
