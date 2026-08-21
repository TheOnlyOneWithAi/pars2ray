from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.entities import Metric, Node, Traffic
from app.services import agent_client
from app.services.benchmark import score_measurement
from app.services.intelligence_cycle import run_intelligence_cycle
from app.services.canary_executor import CanaryExecutionError, execute_canary
from app.services.national_mode import national_engine

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


async def poll_nodes() -> None:
    """Check every configured node once, then stop checking them until restart."""
    db = SessionLocal()
    reachable = 0
    try:
        nodes = db.scalars(select(Node)).all()
        for node in nodes:
            try:
                snapshot = await agent_client.health(node)
                metrics = await agent_client.metrics(node)
                node.status = "ONLINE"
                node.last_seen_at = datetime.utcnow()
                node.cpu_percent = float(metrics.get("cpu_percent", 0))
                node.memory_percent = float(metrics.get("memory_percent", 0))
                node.traffic_rx_bytes = int(metrics.get("traffic_rx_bytes", 0))
                node.traffic_tx_bytes = int(metrics.get("traffic_tx_bytes", 0))
                node.capabilities = snapshot.get("capabilities", {})
                node.core = node.capabilities.get("active_core", node.core)
                node.core_version = node.capabilities.get("core_version", node.core_version)
                node.score = score_measurement(0, 0, 0, 100, 0, node.cpu_percent, node.memory_percent)
                db.add(Metric(node_id=node.id, cpu_percent=node.cpu_percent, memory_percent=node.memory_percent, stability_percent=100))
                db.add(Traffic(node_id=node.id, rx_bytes=node.traffic_rx_bytes, tx_bytes=node.traffic_tx_bytes))
                reachable += 1
            except Exception:
                if node.status != "DRAINING":
                    node.status = "OFFLINE"
        state = national_engine.update_connectivity(db, foreign_reachable=(reachable > 0 or not nodes))
        state.ai_status = "READY" if settings.ai_enabled and settings.openai_api_key else "DISABLED"
        db.commit()
        logger.info("one-shot node check complete: checked=%d reachable=%d", len(nodes), reachable)
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
    if scheduler.running:
        return
    # Node health is intentionally one-shot: all existing nodes are checked once
    # after startup and are not polled again until the master process restarts.
    scheduler.add_job(
        poll_nodes,
        "date",
        run_date=datetime.utcnow() + timedelta(seconds=1),
        id="node-poll-once",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(intelligence_tick, "interval", seconds=max(getattr(settings, "intelligence_interval_seconds", 300), 30), id="intelligence-cycle", replace_existing=True, coalesce=True, max_instances=1)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
