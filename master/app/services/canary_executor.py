from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.security import decrypt_secret
from app.db.base import SessionLocal
from app.models.entities import AuditLog, Experiment, Node, Route
from app.services import agent_client
from app.services.canary_runner import CanaryObservation, CanaryRunner
from app.services.experiment_lab import ExperimentPolicy

logger = logging.getLogger(__name__)


class CanaryExecutionError(RuntimeError):
    pass


def _find_candidate(db, candidate_id: str) -> Route | None:
    try:
        return db.get(Route, int(candidate_id))
    except (TypeError, ValueError):
        return db.scalar(select(Route).where(Route.name == candidate_id))


async def execute_canary(candidate_id: str) -> dict:
    """Run one guarded canary and promote only after deterministic gates pass.

    Auto mutation is opt-in through PARS2RAY_CANARY_AUTO_APPLY. With the default
    value false this service evaluates no node state and never changes production.
    """
    if not getattr(settings, "canary_auto_apply", False):
        return {"action": "DRY_RUN", "candidate_id": candidate_id, "reason": "Canary auto-apply is disabled."}

    db = SessionLocal()
    applied_nodes: list[Node] = []
    try:
        candidate = _find_candidate(db, candidate_id)
        if not candidate:
            raise CanaryExecutionError("candidate route not found")
        if not candidate.node_keys:
            raise CanaryExecutionError("candidate has no nodes")

        active = db.scalar(select(Route).where(Route.is_active.is_(True)).limit(1))
        if not active or active.id == candidate.id:
            raise CanaryExecutionError("candidate must differ from an active route")

        nodes = db.scalars(select(Node).where(Node.node_key.in_(candidate.node_keys), Node.status == "ONLINE")).all()
        if not nodes:
            raise CanaryExecutionError("no online candidate nodes")

        node = nodes[0]
        config = decrypt_secret(candidate.config_enc)
        await agent_client.apply_config(node, {"config": config, "mode": "CANARY"})
        applied_nodes.append(node)

        benchmark = await agent_client.benchmark(node, {"duration_seconds": 10, "mode": "CANARY"})
        observation = CanaryObservation(
            candidate_id=str(candidate.id),
            latency_ms=float(benchmark.get("latency_ms", node.latency_ms or 9999)),
            jitter_ms=float(benchmark.get("jitter_ms", 9999)),
            packet_loss_percent=float(benchmark.get("packet_loss_percent", 100)),
            throughput_mbps=float(benchmark.get("throughput_mbps", 0)),
            stability_percent=float(benchmark.get("stability_percent", 0)),
            availability_percent=float(benchmark.get("availability_percent", 0)),
        )
        policy = ExperimentPolicy(min_improvement=settings.ai_switch_min_improvement, required_wins=settings.ai_required_wins)
        result = CanaryRunner(policy).evaluate(active.score, observation, candidate.consecutive_wins + 1)

        db.add(Experiment(candidate_id=str(candidate.id), route_hash=str(candidate.id), config_hash=str(candidate.id), node_keys=list(candidate.node_keys), core=candidate.core, protocol=candidate.protocol, transport=candidate.transport, score=observation.score, latency_ms=observation.latency_ms, jitter_ms=observation.jitter_ms, packet_loss_percent=observation.packet_loss_percent, throughput_mbps=observation.throughput_mbps, stability_percent=observation.stability_percent, level="CANARY", decision=result.action, metadata_json={"availability_percent": observation.availability_percent}))

        if result.action != "PROMOTE":
            await agent_client.rollback(node)
            applied_nodes.clear()
            # Preserve successful canary streaks; unsafe/failed observations reset it.
            candidate.consecutive_wins = candidate.consecutive_wins + 1 if result.action == "CANARY" else 0
            if result.action == "CANARY":
                candidate.score = result.score
            db.add(AuditLog(action=f"CANARY_{result.action}", resource_type="route", resource_id=str(candidate.id), metadata_json={"score": result.score, "reason": result.reason, "consecutive_wins": candidate.consecutive_wins}))
            db.commit()
            return {"action": result.action, "candidate_id": candidate_id, "score": result.score, "reason": result.reason, "consecutive_wins": candidate.consecutive_wins}

        for remaining in nodes[1:]:
            await agent_client.apply_config(remaining, {"config": config, "mode": "PROMOTE"})
            applied_nodes.append(remaining)

        active.is_active = False
        active.status = "SUPERSEDED"
        candidate.is_active = True
        candidate.status = "ACTIVE"
        candidate.is_golden = True
        candidate.consecutive_wins += 1
        candidate.score = result.score
        db.add(AuditLog(action="CANARY_PROMOTE", resource_type="route", resource_id=str(candidate.id), metadata_json={"score": result.score, "nodes": len(applied_nodes), "consecutive_wins": candidate.consecutive_wins}))
        db.commit()
        return {"action": "PROMOTE", "candidate_id": candidate_id, "score": result.score, "reason": result.reason}
    except Exception as exc:
        db.rollback()
        for node in reversed(applied_nodes):
            try:
                await agent_client.rollback(node)
            except Exception:
                logger.exception("canary rollback failed for node=%s", node.node_key)
        raise CanaryExecutionError(str(exc)) from exc
    finally:
        db.close()


def execute_canary_sync(candidate_id: str) -> dict:
    return asyncio.run(execute_canary(candidate_id))
