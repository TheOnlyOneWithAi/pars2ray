from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, request_ip
from app.db.base import get_db
from app.models.entities import Node, User
from app.services import agent_client
from app.services.audit import record

router = APIRouter(prefix="/api/v1/nodes", tags=["node-operations"])
ROLES = ("SUPER_ADMIN", "ADMIN", "OPERATOR")


def _node(node_key: str, db: Session) -> Node:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    return node


async def _action(node: Node, action: str, payload: dict | None = None) -> dict:
    try:
        return await getattr(agent_client, action)(node, **({"payload": payload} if action == "benchmark" else {})) if action == "benchmark" else await getattr(agent_client, action)(node, **({"lines": int(payload.get("lines", 200))} if action == "logs" else {}))
    except Exception as exc:
        node.status = "OFFLINE"
        raise HTTPException(status_code=502, detail="node_unreachable") from exc


@router.post("/{node_key}/start")
async def start(node_key: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    node = _node(node_key, db)
    result = await _action(node, "start")
    record(db, user, "node.start", "node", str(node.id), request_ip(request))
    db.commit()
    return result


@router.post("/{node_key}/stop")
async def stop(node_key: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    node = _node(node_key, db)
    result = await _action(node, "stop")
    record(db, user, "node.stop", "node", str(node.id), request_ip(request))
    db.commit()
    return result


@router.get("/{node_key}/version")
async def version(node_key: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    node = _node(node_key, db)
    result = await _action(node, "version")
    if result.get("core"):
        node.core = result["core"]
    db.commit()
    return result


@router.get("/{node_key}/logs")
async def logs(node_key: str, lines: int = 200, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    node = _node(node_key, db)
    return await _action(node, "logs", {"lines": max(1, min(lines, 2000))})


@router.post("/{node_key}/update-core")
async def update_core(node_key: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN"))) -> dict:
    node = _node(node_key, db)
    result = await _action(node, "update_core")
    record(db, user, "node.update_core", "node", str(node.id), request_ip(request), {"result": result})
    db.commit()
    return result


@router.get("/{node_key}/firewall")
async def firewall(node_key: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    node = _node(node_key, db)
    return await _action(node, "firewall_status")
