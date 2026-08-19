from dataclasses import dataclass
from app.core.config import settings

@dataclass
class GateResult:
    call_ai: bool
    action: str
    reason: str

def evaluate_gate(current_score: float, previous_score: float | None, anomaly: bool, new_method: bool, route_failed: bool, optimization_requested: bool = False) -> GateResult:
    if optimization_requested:
        return GateResult(True,'ANALYZE','operator_requested_optimization')
    if route_failed: return GateResult(True,'ANALYZE','route_failed')
    if anomaly: return GateResult(True,'ANALYZE','anomaly_detected')
    if new_method: return GateResult(True,'ANALYZE','new_method_detected')
    if previous_score is None: return GateResult(False,'KEEP','no_previous_baseline')
    if abs(current_score-previous_score) < settings.ai_min_score_change:
        return GateResult(False,'KEEP','no_meaningful_change')
    return GateResult(True,'ANALYZE','meaningful_score_change')
