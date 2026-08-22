from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from threading import Lock

from sqlalchemy import select

from app.core.config import settings
from app.core.security import decrypt_secret
from app.db.base import SessionLocal
from app.models.entities import AuditLog, Experiment, Node, Route
from app.services import agent_client
from app.services.canary_runner import CanaryObservation, CanaryRunner
from app.services.experiment_lab import ExperimentPolicy

logger = logging.getLogger(__name__)
_canary_lock = Lock()


class CanaryExecutionError(RuntimeError):
    pass


def _find_candidate(db, candidate_id: str) -> Route | None:
    try:
        return db.get(Route, int(candidate_id))
    except (TypeError, ValueError):
        return db.scalar(select(Route).where(Route.name == candidate_id))


def _stable_hash(value: object) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def execute_canary(candidate_id: str) -> dict:
    """Run one guarded canary and promote only after deterministic gates pass."""
    if not getattr(settings, "canary_auto_apply", False):
        return {"action": "DRY_RUN", "candidate_id": candidate_id, "reason": "Canary auto-apply is disabled."}
    if not _canary_lock.acquire(blocking=False):
        raise CanaryExecutionError("another canary execution is already running")

    db = SessionLocal()
    applied_nodes: list[Node] = []
    operation_ids: dict[str, str] = {}
    try:
        candidate = _find_candidate(db, candidate_id)
        if not candidate:
            raise CanaryExecutionError("candidate route not found")
        candidate_keys = list(dict.fromkeys(str(key).strip() for key in (candidate.node_keys or []) if str(key).strip()))
        if not candidate_keys:
            raise CanaryExecutionError("candidate has no nodes")

        active_routes = db.scalars(select(Route).where(Route.is_active.is_(True))).all()
        if len(active_routes) != 1:
            raise CanaryExecutionError("expected exactly one active route")
        active = active_routes[0]
        if active.id == candidate.id:
            raise CanaryExecutionError("candidate must differ from active route")

        nodes = db.scalars(select(Node).where(Node.node_key.in_(candidate_keys))).all()
        by_key = {node.node_key: node for node in nodes}
        missing = [key for key in candidate_keys if key not in by_key]
        offline = [key for key in candidate_keys if key in by_key and by_key[key].status != "ONLINE"]
        if missing:
            raise CanaryExecutionError(f"candidate_nodes_missing:{','.join(missing)}")
        if offline:
            raise CanaryExecutionError(f"candidate_nodes_not_online:{','.join(offline)}")
        nodes = [by_key[key] for key in candidate_keys]

        config = decrypt_secret(candidate.config_enc)
        config_hash = _stable_hash(config)
        route_hash = _stable_hash({"route_id": candidate.id, "node_keys": candidate_keys, "core": candidate.core, "protocol": candidate.protocol, "transport": candidate.transport})
        node = nodes[0]
        canary_operation = f"canary:{candidate.id}:canary:{config_hash}"
        operation_ids[node.node_key] = canary_operation
        await agent_client.apply_config(node, {"config": config, "mode": "CANARY", "operation_id": canary_operation, "candidate_id": str(candidate.id)})
        applied_nodes.append(node)

        benchmark = await agent_client.benchmark(node, {"duration_seconds": 10, "mode": "CANARY"})
        observation = CanaryObservation(candidate_id=str(candidate.id), latency_ms=float(benchmark.get("latency_ms", node.latency_ms or 9999)), jitter_ms=float(benchmark.get("jitter_ms", 9999)), packet_loss_percent=float(benchmark.get("packet_loss_percent", 100)), throughput_mbps=float(benchmark.get("throughput_mbps", 0)), stability_percent=float(benchmark.get("stability_percent", 0)), availability_percent=float(benchmark.get("availability_percent", 0)))
        policy = ExperimentPolicy(min_improvement=settings.ai_switch_min_improvement, required_wins=settings.ai_required_wins)
        result = CanaryRunner(policy).evaluate(active.score, observation, candidate.consecutive_wins + 1)

        db.add(Experiment(candidate_id=str(candidate.id), route_hash=route_hash, config_hash=config_hash, node_keys=candidate_keys, core=candidate.core, protocol=candidate.protocol, transport=candidate.transport, score=observation.score, latency_ms=observation.latency_ms, jitter_ms=observation.jitter_ms, throughput_mbps=observation.throughput_mbps, packet_loss_percent=observation.packet_loss_percent, stability_percent=observation.stability_percent, level="CANARY", decision=result.action, metadata_json={"availability_percent": observation.availability_percent}))

        if result.action != "PROMOTE":
            rollback_operation = f"{canary_operation}:rollback"
            await agent_client.rollback(node, operation_id=rollback_operation)
            applied_nodes.clear()
            candidate.consecutive_wins = candidate.consecutive_wins + 1 if result.action == "CANARY" else 0
            if result.action == "CANARY":
                candidate.score = result.score
            db.add(AuditLog(action=f"CANARY_{result.action}", resource_type="route", resource_id=str(candidate.id), metadata_json={"score": result.score, "reason": result.reason, "consecutive_wins": candidate.consecutive_wins}))
            db.commit()
            return {"action": result.action, "candidate_id": candidate_id, "score": result.score, "reason": result.reason, "consecutive_wins": candidate.consecutive_wins}

        for remaining in nodes[1:]:
            operation_id = f"canary:{candidate.id}:promote:{remaining.node_key}:{config_hash}"
            operation_ids[remaining.node_key] = operation_id
            await agent_client.apply_config(remaining, {"config": config, "mode": "PROMOTE", "operation_id": operation_id, "candidate_id": str(candidate.id)})
            applied_nodes.append(remaining)

        active.is_active = False
        active.status = "SUPERSEDED"
        candidate.is_active = True
        candidate.status = "ACTIVE"
        candidate.is_golden = True
        candidate.consecutive_wins += 1
        candidate.score = result.score
        db.add(AuditLog(action="CANARY_PROMOTE", resource_type="route", resource_id=str(candidate.id), metadata_json={"score": result.score, "nodes": len(applied_nodes), "consecutive_wins": candidate.consecutive_wins, "route_hash": route_hash, "config_hash": config_hash}))
        db.commit()
        return {"action": "PROMOTE", "candidate_id": candidate_id, "score": result.score, "reason": result.reason}
    except Exception as exc:
        db.rollback()
        for node in reversed(applied_nodes):
            try:
                base_operation = operation_ids.get(node.node_key, f"canary:{candidate_id}:{node.node_key}")
                await agent_client.rollback(node, operation_id=f"{base_operation}:rollback")
            except Exception:
                logger.exception("canary rollback failed for node=%s", node.node_key)
        raise CanaryExecutionError(str(exc)) from exc
    finally:
        db.close()
        _canary_lock.release()


def execute_canary_sync(candidate_id: str) -> dict:
    return asyncio.run(execute_canary(candidate_id))
