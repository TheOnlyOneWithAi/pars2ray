from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import desc, select

from app.db.base import SessionLocal
from app.models.entities import Experiment, Route


def golden_candidates(limit: int = 10) -> list[dict]:
    """Return proven routes first; never expose encrypted route configuration."""
    db = SessionLocal()
    try:
        routes = db.scalars(select(Route).where(Route.is_golden.is_(True)).order_by(desc(Route.score), desc(Route.consecutive_wins)).limit(max(1, min(limit, 50)))).all()
        return [{"route_id": route.id, "name": route.name, "score": route.score, "core": route.core, "protocol": route.protocol, "transport": route.transport, "consecutive_wins": route.consecutive_wins} for route in routes]
    finally:
        db.close()


def promote_golden(route_id: int, min_wins: int = 3, min_score: float = 80.0) -> bool:
    """Promote only a consistently successful route; caller remains responsible for production gate."""
    db = SessionLocal()
    try:
        route = db.get(Route, route_id)
        if not route or route.score < min_score or route.consecutive_wins < min_wins:
            return False
        route.is_golden = True
        route.status = "GOLDEN"
        db.commit()
        return True
    finally:
        db.close()


def historical_outcomes(candidate_id: str, days: int = 30, limit: int = 20) -> list[dict]:
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
        rows = db.scalars(select(Experiment).where(Experiment.candidate_id == candidate_id, Experiment.created_at >= cutoff).order_by(desc(Experiment.created_at)).limit(max(1, min(limit, 100)))).all()
        return [{"score": row.score, "decision": row.decision, "level": row.level, "latency_ms": row.latency_ms, "jitter_ms": row.jitter_ms, "packet_loss_percent": row.packet_loss_percent, "stability_percent": row.stability_percent, "created_at": row.created_at.isoformat()} for row in rows]
    finally:
        db.close()
