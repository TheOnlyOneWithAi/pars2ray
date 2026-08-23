from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, request_ip, require_roles
from app.db.base import get_db
from app.models.entities import User
from app.services.ai_autopilot import policy, run
from app.services.audit import record

router = APIRouter(prefix="/api/v1/ai", tags=["ai-autopilot"])


class RunRequest(BaseModel):
    dry_run: bool = True


@router.get("/policy")
def get_policy(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    p = policy(db)
    return {"level": p.level, "autonomous": p.autonomous, "probe_country": p.probe_country, "max_nodes": p.max_nodes, "max_candidates": p.max_candidates}


@router.post("/autopilot/run")
async def run_autopilot(payload: RunRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN"))) -> dict:
    try:
        result = await run(db, user, dry_run=payload.dry_run)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ai_autopilot_failed:{exc}") from exc
    record(db, user, "ai.autopilot.run", "ai", "autopilot", request_ip(request), {"dry_run": payload.dry_run, "created": len(result.get("created", [])), "tested": len(result.get("tested", []))})
    db.commit()
    return result
