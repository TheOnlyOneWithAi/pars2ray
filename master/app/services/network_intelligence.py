from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import desc, select

from app.db.base import SessionLocal
from app.models.entities import Decision, Experiment, Metric, Route


@dataclass(frozen=True)
class RouteScore:
    availability: float
    latency: float
    jitter: float
    loss: float
    throughput: float
    stability: float

    @property
    def total(self) -> float:
        # Availability/stability dominate; latency/loss matter more than raw throughput.
        return round(self.availability * 0.30 + self.stability * 0.25 + self.loss * 0.15 + self.latency * 0.12 + self.jitter * 0.10 + self.throughput * 0.08, 2)


def _bounded_inverse(value: float, good: float, bad: float) -> float:
    if value <= good:
        return 100.0
    if value >= bad:
        return 0.0
    return max(0.0, min(100.0, (bad - value) / (bad - good) * 100.0))


def score_metrics(latency_ms: float, jitter_ms: float, loss_percent: float, throughput_mbps: float, stability_percent: float, availability_percent: float = 100.0) -> RouteScore:
    return RouteScore(
        availability=max(0.0, min(100.0, availability_percent)),
        latency=_bounded_inverse(latency_ms, 60.0, 350.0),
        jitter=_bounded_inverse(jitter_ms, 8.0, 100.0),
        loss=_bounded_inverse(loss_percent, 0.2, 8.0),
        throughput=max(0.0, min(100.0, throughput_mbps / 2.0)),
        stability=max(0.0, min(100.0, stability_percent)),
    )


def build_intelligence_snapshot(route_id: int | None = None, hours: int = 24) -> dict:
    """Return local, provider-free evidence for the decision engine."""
    cutoff = datetime.utcnow() - timedelta(hours=max(1, min(hours, 168)))
    db = SessionLocal()
    try:
        route = db.get(Route, route_id) if route_id else db.scalar(select(Route).where(Route.is_active.is_(True)).limit(1))
        if not route:
            return {"current_route": {}, "candidates": [], "current_score": 0.0, "previous_score": 0.0, "trigger": "no_active_route"}
        experiments = db.scalars(select(Experiment).where(Experiment.created_at >= cutoff).order_by(desc(Experiment.created_at)).limit(100)).all()
        candidates = []
        seen: set[str] = set()
        for item in experiments:
            if item.candidate_id in seen:
                continue
            seen.add(item.candidate_id)
            candidates.append({"candidate_id": item.candidate_id, "core": item.core, "protocol": item.protocol, "transport": item.transport, "score": item.score, "latency_ms": item.latency_ms, "jitter_ms": item.jitter_ms, "packet_loss_percent": item.packet_loss_percent, "throughput_mbps": item.throughput_mbps, "stability_percent": item.stability_percent, "node_count": len(item.node_keys or [])})
        previous = db.scalar(select(Decision).order_by(desc(Decision.created_at)).limit(1))
        return {"current_route": {"route_id": str(route.id), "route_hash": str(route.id), "core": route.core, "protocol": route.protocol, "transport": route.transport, "score": route.score, "status": route.status}, "candidates": candidates, "current_score": route.score, "previous_score": previous.proposed_score if previous else route.score, "trigger": "scheduled_intelligence_cycle"}
    finally:
        db.close()
