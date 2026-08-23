from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.entities import Node
from app.services.ai_autopilot import policy, run

logger = logging.getLogger(__name__)


async def on_iran_node_disconnect(db: Session, node: Node) -> dict:
    """Build fallback inbounds after an Iranian node loses master access.

    The scheduler calls this only for an ONLINE/REGISTERED -> OFFLINE edge.
    The disconnected node is never selected as a deployment target. A different
    reachable Iranian node remains the preferred benchmark source; otherwise
    the best reachable managed node becomes the temporary probe.
    """
    if node.country.upper() != "IR":
        return {"triggered": False, "reason": "not_iran_node"}

    current = policy(db)
    if current.level < 4 or not current.autonomous:
        return {"triggered": False, "reason": "ai_autonomous_mode_disabled"}

    logger.warning(
        "Iran node %s lost master connectivity; autonomous AI failover starting",
        node.node_key,
    )
    result = await run(
        db,
        None,
        dry_run=False,
        internal_trigger="iran_node_disconnect",
    )
    return {
        "triggered": True,
        "reason": "iran_node_disconnected",
        "disconnected_node": node.node_key,
        "result": result,
    }
