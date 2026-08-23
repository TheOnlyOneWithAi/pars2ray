from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, request_ip, require_roles
from app.db.base import get_db
from app.models.entities import Node, User
from app.services import agent_client
from app.services.ai_autopilot import policy
from app.services.audit import record
from app.services.openai_inbound_optimizer import suggest

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class ConfigureNodeRequest(BaseModel):
    node_key: str = Field(min_length=2, max_length=40)
    apply: bool = True
    telemetry: dict = Field(default_factory=dict)


@router.post("/configure-node", dependencies=[Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))])
async def configure_node(payload: ConfigureNodeRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if policy(db).level < 2:
        raise HTTPException(status_code=403, detail="ai_permission_level_too_low_for_inbound_management")
    node = db.scalar(select(Node).where(Node.node_key == payload.node_key.upper()))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    try:
        current = await agent_client.config(node)
        core = str(current.get("core", "none"))
        inbounds = current.get("inbounds", [])
        if not inbounds:
            raise HTTPException(status_code=409, detail="node_has_no_existing_inbounds")
        decision, usage = await suggest(core, inbounds, payload.telemetry)
        existing_tags = {str(item.get("tag")) for item in inbounds}
        updates = decision.get("updates", [])
        if any(str(item.get("tag")) not in existing_tags for item in updates):
            raise HTTPException(status_code=422, detail="ai_proposed_unknown_inbound")
        if not payload.apply:
            return {"ok": True, "applied": False, "core": core, "updates": updates, "reason": decision.get("reason", ""), "usage": usage}
        result = await agent_client.update_existing_inbounds(node, updates)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("reason", "inbound_update_failed"))
        record(db, user, "ai.inbound_update", "node", str(node.id), request_ip(request), {"tags": result.get("updated_tags", []), "core": core})
        db.commit()
        return {"ok": True, "applied": True, "core": core, "updates": updates, "result": result, "reason": decision.get("reason", ""), "usage": usage}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ai_configuration_failed:{exc}") from exc
