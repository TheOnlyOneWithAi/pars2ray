from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.entities import Node
from app.services.ai_autopilot import policy, run

logger = logging.getLogger(__name__)


async def on_iran_node_disconnect(db: Session, node: Node) -> dict:
    """Build a fallback inbound set when an Iranian management node drops.

    The trigger is edge-based: callers invoke this only on ONLINE/REGISTERED ->
    OFFLINE transitions, so an already-offline node cannot repeatedly trigger
    autonomous changes every polling cycle.

    The disconnected node is never selected as a deployment target. If another
    reachable Iranian node exists it remains the preferred benchmark source;
    otherwise the best reachable managed node becomes the temporary probe.
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
    result = await run(db, None, dry_run=False)
    return {
        "triggered": True,
        "reason": "iran_node_disconnected",
        "disconnected_node": node.node_key,
        "result": result,
    }
