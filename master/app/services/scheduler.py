from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.entities import Metric, Node, Subscription, Traffic, User
from app.services import agent_client
from app.services.ai_failover import on_iran_node_disconnect
from app.services.intelligence_cycle import run_intelligence_cycle
from app.services.canary_executor import CanaryExecutionError, execute_canary
from app.services.national_mode import national_engine

logger = logging.getLogger(__name__)
scheduler: AsyncIOScheduler | None = None
BYTES_PER_GB = 1024**3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _counter_delta(current: int, previous: int) -> int:
    """Return a safe monotonic delta; a reset is treated as a new baseline."""
    current = max(int(current), 0)
    previous = max(int(previous), 0)
    return current - previous if current >= previous else 0


def _record_usage_delta(db, node: Node, delta_bytes: int) -> None:
    """Apply node traffic deltas to every matching subscription exactly once."""
    if delta_bytes <= 0:
        return
    delta_gb = delta_bytes / BYTES_PER_GB
    subscriptions = db.scalars(
        select(Subscription).where(Subscription.enabled.is_(True))
    ).all()
    users_seen: set[int] = set()
    for subscription in subscriptions:
        allowed = {
            str(key).strip().upper()
            for key in (subscription.node_keys or [])
            if str(key).strip()
        }
        if allowed and node.node_key.upper() not in allowed:
            continue
        subscription.used_gb = max(float(subscription.used_gb or 0), 0.0) + delta_gb
        if subscription.user_id not in users_seen:
            target = db.get(User, subscription.user_id)
            if target is not None:
                target.used_gb = max(float(target.used_gb or 0), 0.0) + delta_gb
            users_seen.add(subscription.user_id)


async def poll_nodes() -> None:
    """Poll every configured node and trigger Iran failover on a real edge."""
    db = SessionLocal()
    reachable = 0
    try:
        nodes = db.scalars(select(Node)).all()
        now = _utcnow()
        failover_nodes: list[Node] = []
        for node in nodes:
            was_draining = node.status == "DRAINING"
            was_reachable = node.status in {"ONLINE", "REGISTERED"}
            previous_rx = max(int(node.traffic_rx_bytes or 0), 0)
            previous_tx = max(int(node.traffic_tx_bytes or 0), 0)
            try:
                snapshot = await agent_client.health(node)
                metrics = await agent_client.metrics(node)
                node.status = "DRAINING" if was_draining else "ONLINE"
                node.last_seen_at = now
                node.cpu_percent = max(float(metrics.get("cpu_percent", 0)), 0)
                node.memory_percent = max(float(metrics.get("memory_percent", 0)), 0)
                node.traffic_rx_bytes = max(int(metrics.get("traffic_rx_bytes", 0)), 0)
                node.traffic_tx_bytes = max(int(metrics.get("traffic_tx_bytes", 0)), 0)
                delta_rx = _counter_delta(node.traffic_rx_bytes, previous_rx)
                delta_tx = _counter_delta(node.traffic_tx_bytes, previous_tx)
                _record_usage_delta(db, node, delta_rx + delta_tx)
                node.capabilities = snapshot.get("capabilities", {})
                node.core = node.capabilities.get("active_core", node.core)
                node.core_version = node.capabilities.get("core_version", node.core_version)
                db.add(
                    Metric(
                        node_id=node.id,
                        cpu_percent=node.cpu_percent,
                        memory_percent=node.memory_percent,
                        stability_percent=100,
                    )
                )
                db.add(
                    Traffic(
                        node_id=node.id,
                        rx_bytes=node.traffic_rx_bytes,
                        tx_bytes=node.traffic_tx_bytes,
                    )
                )
                reachable += 1
            except Exception:
                if not was_draining:
                    node.status = "OFFLINE"
                if node.country.upper() == "IR" and was_reachable:
                    failover_nodes.append(node)

        state = national_engine.update_connectivity(
            db,
            foreign_reachable=(reachable > 0 or not nodes),
        )
        state.ai_status = "READY" if settings.ai_enabled and settings.openai_api_key else "DISABLED"
        db.commit()

        for node in failover_nodes:
            try:
                result = await on_iran_node_disconnect(db, node)
                logger.warning(
                    "Iran node failover completed node=%s triggered=%s created=%d",
                    node.node_key,
                    result.get("triggered", False),
                    len(result.get("result", {}).get("created", [])),
                )
            except Exception:
                logger.exception(
                    "Iran node failover failed node=%s; scheduler will continue",
                    node.node_key,
                )

        logger.info(
            "node health poll complete: checked=%d reachable=%d iran_failovers=%d",
            len(nodes),
            reachable,
            len(failover_nodes),
        )
    finally:
        db.close()


async def intelligence_tick() -> None:
    """Run decision and, when explicitly enabled, execute a guarded canary."""
    try:
        decision = await run_intelligence_cycle()
        logger.info(
            "intelligence decision action=%s candidate=%s",
            decision.action,
            decision.candidate_id,
        )
        if decision.candidate_id and decision.action in {"TEST", "CANARY"}:
            result = await execute_canary(str(decision.candidate_id))
            logger.info(
                "canary result action=%s candidate=%s",
                result.get("action"),
                decision.candidate_id,
            )
    except CanaryExecutionError:
        logger.exception("canary execution failed; production route was not promoted")
    except Exception:
        logger.exception("intelligence cycle failed; scheduler will continue")


def start_scheduler() -> None:
    global scheduler
    if scheduler is not None and scheduler.running:
        return

    loop = asyncio.get_running_loop()
    scheduler = AsyncIOScheduler(event_loop=loop, timezone="UTC")
    poll_seconds = max(int(getattr(settings, "node_poll_seconds", 30)), 5)
    scheduler.add_job(
        poll_nodes,
        "interval",
        seconds=poll_seconds,
        id="node-poll",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=poll_seconds,
    )
    scheduler.add_job(
        intelligence_tick,
        "interval",
        seconds=max(getattr(settings, "intelligence_interval_seconds", 300), 30),
        id="intelligence-cycle",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=30,
    )
    scheduler.start()


def stop_scheduler() -> None:
    global scheduler
    current = scheduler
    scheduler = None
    if current is not None and current.running:
        current.shutdown(wait=False)
