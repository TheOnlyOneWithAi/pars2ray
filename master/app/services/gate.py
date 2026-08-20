from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class GateResult:
    call_ai: bool
    action: str
    reason: str


def evaluate_gate(current_score: float, previous_score: float | None, anomaly: bool, new_method: bool, route_failed: bool, optimization_requested: bool = False) -> GateResult:
    try:
        current = float(current_score)
    except (TypeError, ValueError):
        return GateResult(False, "KEEP", "invalid_current_score")
    if not math.isfinite(current):
        return GateResult(False, "KEEP", "invalid_current_score")
    if optimization_requested:
        return GateResult(True, "ANALYZE", "operator_requested_optimization")
    if route_failed:
        return GateResult(True, "ANALYZE", "route_failed")
    if anomaly:
        return GateResult(True, "ANALYZE", "anomaly_detected")
    if new_method:
        return GateResult(True, "ANALYZE", "new_method_detected")
    if previous_score is None:
        return GateResult(False, "KEEP", "no_previous_baseline")
    try:
        previous = float(previous_score)
    except (TypeError, ValueError):
        return GateResult(False, "KEEP", "invalid_previous_score")
    if not math.isfinite(previous):
        return GateResult(False, "KEEP", "invalid_previous_score")
    threshold = max(0.0, float(settings.ai_min_score_change))
    if abs(current - previous) < threshold:
        return GateResult(False, "KEEP", "no_meaningful_change")
    return GateResult(True, "ANALYZE", "meaningful_score_change")
