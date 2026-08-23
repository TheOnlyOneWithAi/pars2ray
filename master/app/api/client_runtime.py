from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, request_ip
from app.db.base import get_db
from app.models.entities import Subscription, User
from app.models.runtime import ClientRuntime
from app.services.audit import record

router = APIRouter(prefix="/api/v1/clients", tags=["client-runtime"])
ROLES = ("SUPER_ADMIN", "ADMIN", "RESELLER")


def _client(client_id: int, db: Session) -> Subscription:
    client = db.get(Subscription, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="client_not_found")
    return client


def _owner(user: User, client: Subscription) -> None:
    if user.role == "RESELLER" and client.user_id != user.id:
        raise HTTPException(status_code=403, detail="forbidden")


def _runtime(db: Session, client_id: int) -> ClientRuntime:
    row = db.scalar(select(ClientRuntime).where(ClientRuntime.subscription_id == client_id))
    if not row:
        row = ClientRuntime(subscription_id=client_id, ip_limit=0, online_ips=[], last_online_at=None)
        db.add(row)
        db.flush()
    return row


@router.get("/{client_id}/runtime")
def runtime(client_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    client = _client(client_id, db)
    _owner(user, client)
    row = _runtime(db, client_id)
    db.commit()
    return {"client_id": client_id, "ip_limit": row.ip_limit, "online_ips": list(row.online_ips or []), "online_count": len(row.online_ips or []), "last_online_at": row.last_online_at}


@router.put("/{client_id}/ip-limit")
def set_ip_limit(client_id: int, payload: dict, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    client = _client(client_id, db)
    _owner(user, client)
    try:
        limit = int(payload.get("ip_limit", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="ip_limit_must_be_integer") from exc
    if not 0 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="ip_limit_out_of_range")
    row = _runtime(db, client_id)
    if limit > 0 and len(row.online_ips or []) > limit:
        row.online_ips = list(row.online_ips or [])[:limit]
    row.ip_limit = limit
    record(db, user, "client.ip_limit.update", "client", str(client_id), request_ip(request), {"ip_limit": limit})
    db.commit()
    return {"ok": True, "client_id": client_id, "ip_limit": limit, "online_ips": row.online_ips}


@router.post("/{client_id}/runtime/observe-ip")
def observe_ip(client_id: int, payload: dict, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    client = _client(client_id, db)
    _owner(user, client)
    ip = str(payload.get("ip", "")).strip()
    if not ip or len(ip) > 64:
        raise HTTPException(status_code=422, detail="invalid_ip")
    row = _runtime(db, client_id)
    ips = list(dict.fromkeys([*row.online_ips, ip]))
    if row.ip_limit > 0 and len(ips) > row.ip_limit:
        raise HTTPException(status_code=409, detail="client_ip_limit_exceeded")
    row.online_ips = ips
    row.last_online_at = datetime.utcnow()
    record(db, user, "client.ip.observe", "client", str(client_id), request_ip(request), {"ip": ip})
    db.commit()
    return {"ok": True, "client_id": client_id, "online_ips": ips, "online_count": len(ips), "ip_limit": row.ip_limit}


@router.post("/{client_id}/runtime/reset-ips")
def reset_ips(client_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROLES))) -> dict:
    client = _client(client_id, db)
    _owner(user, client)
    row = _runtime(db, client_id)
    row.online_ips = []
    row.last_online_at = None
    record(db, user, "client.ip.reset", "client", str(client_id), request_ip(request))
    db.commit()
    return {"ok": True, "client_id": client_id, "online_ips": []}
