from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.entities import Decision
from app.services.experiment_lab import ExperimentPolicy
from app.services.golden_memory import golden_candidates
from app.services.network_intelligence import build_intelligence_snapshot
from app.services.openai_optimizer import analyze


@dataclass(frozen=True)
class IntelligenceResult:
    action: str
    candidate_id: str | None
    confidence: float
    reason: str
    ai_called: bool


async def run_cycle(route_id: int | None = None) -> IntelligenceResult:
    """Run one bounded decision cycle. AI advises; local policy remains authoritative."""
    snapshot = build_intelligence_snapshot(route_id=route_id)
    snapshot["golden_candidates"] = golden_candidates(limit=10)
    current_score = float(snapshot.get("current_score") or 0.0)
    candidates = snapshot.get("candidates") or []
    best = max(candidates, key=lambda item: float(item.get("score") or 0.0), default=None)
    best_score = float(best.get("score") or 0.0) if best else current_score
    best_loss = float(best.get("packet_loss_percent") or 0.0) if best else 0.0

    # First gate is deterministic and cheap. This prevents unnecessary model calls.
    local = ExperimentPolicy(min_improvement=settings.ai_switch_min_improvement, required_wins=settings.ai_required_wins, max_loss_percent=5.0)
    if not best or best_score <= current_score:
        action, candidate_id, confidence, reason = "KEEP", None, 1.0, "No candidate currently beats the active route."
        ai_called = False
    elif best_loss > 5.0:
        action, candidate_id, confidence, reason = "KEEP", None, 1.0, "Best candidate exceeds the packet-loss safety ceiling."
        ai_called = False
    elif not settings.ai_enabled or not settings.openai_api_key:
        action = local.decision(current_score, best_score, best_loss, wins=0)
        candidate_id, confidence, reason, ai_called = best.get("candidate_id"), 0.75, "Local optimizer selected the candidate; AI is disabled.", False
    else:
        decision, usage = await analyze(snapshot)
        proposed = str(decision.get("action", "KEEP"))
        # AI cannot bypass the deterministic safety gate.
        allowed = {"KEEP", "TEST", "CANARY", "SWITCH", "ROLLBACK"}
        action = proposed if proposed in allowed else "KEEP"
        if action == "SWITCH" and best_score < current_score + settings.ai_switch_min_improvement:
            action = "CANARY"
        if action in {"SWITCH", "CANARY", "TEST"} and best_loss > 5.0:
            action = "KEEP"
        candidate_id = decision.get("candidate_id") if action != "KEEP" else None
        confidence = float(decision.get("confidence") or 0.0)
        reason = str(decision.get("reason") or "AI provided no explanation.")[:500]
        ai_called = True

    db = SessionLocal()
    try:
        row = Decision(current_score=current_score, proposed_score=best_score, action=action, candidate_id=candidate_id, reason=reason, ai_called=ai_called, model=settings.openai_model if ai_called else "")
        db.add(row)
        db.commit()
    finally:
        db.close()
    return IntelligenceResult(action=action, candidate_id=candidate_id, confidence=confidence, reason=reason, ai_called=ai_called)
