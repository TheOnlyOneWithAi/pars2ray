from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.db.base import SessionLocal
from app.models.entities import Experiment, Route


@dataclass(frozen=True)
class ExperimentPolicy:
    min_improvement: float = 10.0
    required_wins: int = 3
    max_loss_percent: float = 5.0

    def decision(self, current_score: float, candidate_score: float, loss_percent: float, wins: int) -> str:
        delta = candidate_score - current_score
        if loss_percent > self.max_loss_percent:
            return "ROLLBACK"
        if delta < self.min_improvement:
            return "KEEP"
        if wins < self.required_wins:
            return "CANARY"
        return "PROMOTE"


def record_result(candidate_id: str, route: Route, score: float, latency_ms: float, jitter_ms: float, loss_percent: float, throughput_mbps: float, stability_percent: float, decision: str, metadata: dict | None = None) -> int:
    """Persist an experiment result without persisting secrets in metadata."""
    safe_metadata = {str(k): v for k, v in (metadata or {}).items() if str(k).lower() not in {"password", "passwd", "secret", "token", "api_key", "config"}}
    db = SessionLocal()
    try:
        row = Experiment(candidate_id=candidate_id, route_hash=str(route.id), config_hash=str(route.id), node_keys=list(route.node_keys or []), core=route.core, protocol=route.protocol, transport=route.transport, score=score, latency_ms=latency_ms, jitter_ms=jitter_ms, packet_loss_percent=loss_percent, throughput_mbps=throughput_mbps, stability_percent=stability_percent, level="EXPERIMENTAL", decision=decision, metadata_json=safe_metadata)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()
