from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, request_ip, require_roles
from app.core.security import random_token, token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Plan, Subscription, User
from app.schemas import ClientCreate, ClientOut, ClientUpdate
from app.services.audit import record
from app.api.protocols import _client_id

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


def _get_client(db: Session, client_id: int) -> Subscription:
    client = db.get(Subscription, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="client_not_found")
    return client


def _out(db: Session, client: Subscription) -> ClientOut:
    plan = db.get(Plan, client.plan_id)
    return ClientOut(
        id=client.id,
        user_id=client.user_id,
        username=(db.get(User, client.user_id).username if db.get(User, client.user_id) else ""),
        plan_id=client.plan_id,
        plan_name=plan.name if plan else "",
        client_id=_client_id(client.token_hash),
        node_keys=list(client.node_keys or []),
        enabled=client.enabled,
        used_gb=max(float(client.used_gb or 0), 0),
        quota_gb=max(float(plan.quota_gb if plan else 0), 0),
        expires_at=client.expires_at,
        created_at=client.created_at,
    )


@router.get("", response_model=list[ClientOut])
def list_clients(
    search: str = "",
    enabled: bool | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ClientOut]:
    limit = min(max(limit, 1), 500)
    query = select(Subscription).order_by(Subscription.id.desc()).limit(limit)
    if enabled is not None:
        query = query.where(Subscription.enabled.is_(enabled))
    if search.strip():
        query = query.join(User, User.id == Subscription.user_id).where(User.username.ilike(f"%{search.strip()}%"))
    clients = db.scalars(query).all()
    return [_out(db, client) for client in clients]


@router.post("", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER")),
) -> ClientOut:
    target = db.get(User, payload.user_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="user_not_found")
    plan = db.get(Plan, payload.plan_id)
    if not plan or not plan.enabled:
        raise HTTPException(status_code=404, detail="plan_not_found")
    if user.role == "RESELLER" and target.id != user.id:
        raise HTTPException(status_code=403, detail="reseller_can_only_manage_self")
    active_for_user = db.scalar(select(Subscription).where(Subscription.user_id == target.id, Subscription.enabled.is_(True)))
    if active_for_user and payload.single_active:
        raise HTTPException(status_code=409, detail="active_client_exists")
    node_keys = list(dict.fromkeys(key.strip().upper() for key in payload.node_keys if key.strip()))
    if len(node_keys) > 20:
        raise HTTPException(status_code=422, detail="too_many_nodes")
    token = random_token(48)
    expires_at = payload.expires_at or (utcnow() + timedelta(days=plan.duration_days))
    if expires_at <= utcnow():
        raise HTTPException(status_code=422, detail="expires_at_must_be_future")
    client = Subscription(
        user_id=target.id,
        plan_id=plan.id,
        token_hash=token_hash(token),
        node_keys=node_keys,
        enabled=True,
        used_gb=0,
        expires_at=expires_at,
    )
    db.add(client)
    db.flush()
    record(db, user, "client.create", "client", str(client.id), request_ip(request), {"user_id": target.id})
    db.commit()
    db.refresh(client)
    return _out(db, client)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    payload: ClientUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER")),
) -> ClientOut:
    client = _get_client(db, client_id)
    if user.role == "RESELLER" and client.user_id != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    if payload.plan_id is not None:
        plan = db.get(Plan, payload.plan_id)
        if not plan or not plan.enabled:
            raise HTTPException(status_code=404, detail="plan_not_found")
        client.plan_id = plan.id
    if payload.node_keys is not None:
        keys = list(dict.fromkeys(key.strip().upper() for key in payload.node_keys if key.strip()))
        if len(keys) > 20:
            raise HTTPException(status_code=422, detail="too_many_nodes")
        client.node_keys = keys
    if payload.enabled is not None:
        client.enabled = payload.enabled
    if payload.expires_at is not None:
        if payload.expires_at <= utcnow():
            raise HTTPException(status_code=422, detail="expires_at_must_be_future")
        client.expires_at = payload.expires_at
    record(db, user, "client.update", "client", str(client.id), request_ip(request))
    db.commit()
    db.refresh(client)
    return _out(db, client)


@router.post("/{client_id}/reset-traffic", response_model=ClientOut)
def reset_client_traffic(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER")),
) -> ClientOut:
    client = _get_client(db, client_id)
    if user.role == "RESELLER" and client.user_id != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    client.used_gb = 0
    record(db, user, "client.traffic_reset", "client", str(client.id), request_ip(request))
    db.commit()
    db.refresh(client)
    return _out(db, client)


@router.delete("/{client_id}")
def delete_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER")),
) -> dict[str, bool]:
    client = _get_client(db, client_id)
    if user.role == "RESELLER" and client.user_id != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    record(db, user, "client.delete", "client", str(client.id), request_ip(request))
    db.delete(client)
    db.commit()
    return {"ok": True}
