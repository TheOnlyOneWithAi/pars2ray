from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.entities import Metric, Node, Traffic
from app.services import agent_client
from app.services.benchmark import score_measurement
from app.services.health_probe import probe_node
from app.services.intelligence_cycle import run_intelligence_cycle
from app.services.national_mode import national_engine

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


async def poll_nodes() -> None:
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
    finally:
        db.close()


async def intelligence_tick() -> None:
    """Run one bounded decision cycle after telemetry polling has had a chance to update state."""
    try:
        decision = await run_intelligence_cycle()
        logger.info("intelligence decision action=%s candidate=%s", decision.action, decision.candidate_id)
    except Exception:
        logger.exception("intelligence cycle failed; scheduler will continue")


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(poll_nodes, "interval", seconds=max(settings.node_poll_seconds, 15), id="node-poll", replace_existing=True, coalesce=True, max_instances=1)
    scheduler.add_job(intelligence_tick, "interval", seconds=max(getattr(settings, "intelligence_interval_seconds", 300), 30), id="intelligence-cycle", replace_existing=True, coalesce=True, max_instances=1)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
