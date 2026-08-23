from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.entities import Metric, Node, Traffic
from app.services import agent_client
from app.services.intelligence_cycle import run_intelligence_cycle
from app.services.canary_executor import CanaryExecutionError, execute_canary
from app.services.national_mode import national_engine

logger = logging.getLogger(__name__)
scheduler: AsyncIOScheduler | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def poll_nodes() -> None:
    """Poll every configured node and persist authoritative health/resource state.

    A node's benchmark score is deliberately not recomputed from resource-only
    telemetry: benchmark quality and liveness are different signals. Manual or
    scheduled benchmark results own ``Node.score``; this poll only updates the
    live health/resource counters.
    """
    db = SessionLocal()
    reachable = 0
    try:
        nodes = db.scalars(select(Node)).all()
        now = _utcnow()
        for node in nodes:
            was_draining = node.status == "DRAINING"
            try:
                snapshot = await agent_client.health(node)
                metrics = await agent_client.metrics(node)
                node.status = "DRAINING" if was_draining else "ONLINE"
                node.last_seen_at = now
                node.cpu_percent = max(float(metrics.get("cpu_percent", 0)), 0)
                node.memory_percent = max(float(metrics.get("memory_percent", 0)), 0)
                node.traffic_rx_bytes = max(int(metrics.get("traffic_rx_bytes", 0)), 0)
                node.traffic_tx_bytes = max(int(metrics.get("traffic_tx_bytes", 0)), 0)
                node.capabilities = snapshot.get("capabilities", {})
                node.core = node.capabilities.get("active_core", node.core)
                node.core_version = node.capabilities.get("core_version", node.core_version)
                # Do not overwrite a benchmark-derived score with synthetic
                # values based only on CPU/RAM. Keep the last authoritative
                # benchmark score until a new benchmark is completed.
                db.add(Metric(node_id=node.id, cpu_percent=node.cpu_percent, memory_percent=node.memory_percent, stability_percent=100))
                db.add(Traffic(node_id=node.id, rx_bytes=node.traffic_rx_bytes, tx_bytes=node.traffic_tx_bytes))
                reachable += 1
            except Exception:
                if not was_draining:
                    node.status = "OFFLINE"
        state = national_engine.update_connectivity(db, foreign_reachable=(reachable > 0 or not nodes))
        state.ai_status = "READY" if settings.ai_enabled and settings.openai_api_key else "DISABLED"
        db.commit()
        logger.info("node health poll complete: checked=%d reachable=%d", len(nodes), reachable)
    finally:
        db.close()


async def intelligence_tick() -> None:
    """Run decision and, when explicitly enabled, execute a guarded canary."""
    try:
        decision = await run_intelligence_cycle()
        logger.info("intelligence decision action=%s candidate=%s", decision.action, decision.candidate_id)
        if decision.candidate_id and decision.action in {"TEST", "CANARY"}:
            result = await execute_canary(str(decision.candidate_id))
            logger.info("canary result action=%s candidate=%s", result.get("action"), decision.candidate_id)
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
