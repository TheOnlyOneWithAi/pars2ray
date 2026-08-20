from __future__ import annotations

import math
from dataclasses import dataclass

from app.db.base import SessionLocal
from app.models.entities import Experiment, Route


@dataclass(frozen=True)
class ExperimentPolicy:
    min_improvement: float = 10.0
    required_wins: int = 3
    max_loss_percent: float = 5.0
    min_stability_percent: float = 95.0

    def decision(self, current_score: float, candidate_score: float, loss_percent: float, wins: int, stability_percent: float = 100.0) -> str:
        """Deterministic safety policy. AI cannot bypass these gates."""
        values = (current_score, candidate_score, loss_percent, stability_percent)
        if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values):
            return "ROLLBACK"
        if not isinstance(wins, int) or wins < 0:
            return "ROLLBACK"
        delta = float(candidate_score) - float(current_score)
        if float(loss_percent) > self.max_loss_percent or float(stability_percent) < self.min_stability_percent:
            return "ROLLBACK"
        if delta < self.min_improvement:
            return "KEEP"
        if wins < self.required_wins:
            return "CANARY"
        return "PROMOTE"


def record_result(candidate_id: str, route: Route, score: float, latency_ms: float, jitter_ms: float, loss_percent: float, throughput_mbps: float, stability_percent: float, decision: str, metadata: dict | None = None) -> int:
    """Persist an experiment result without persisting secrets in metadata."""
    safe_metadata = {str(k): v for k, v in (metadata or {}).items() if str(k).lower() not in {"password", "passwd", "secret", "token", "api_key", "config", "credentials"}}
    db = SessionLocal()
    try:
        row = Experiment(candidate_id=candidate_id, route_hash=str(route.id), config_hash=str(route.id), node_keys=list(route.node_keys or []), core=route.core, protocol=route.protocol, transport=route.transport, score=score, latency_ms=latency_ms, jitter_ms=jitter_ms, packet_loss_percent=loss_percent, throughput_mbps=throughput_mbps, stability_percent=stability_percent, level="EXPERIMENTAL", decision=decision, metadata_json=safe_metadata)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()
