from __future__ import annotations

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, request_ip, require_roles
from app.core.security import random_token, token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Plan, Subscription, User
from app.schemas import ClientCreate, ClientOut, ClientUpdate
from app.services.audit import record

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


def _client_id(token_hash_value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pars2ray:{token_hash_value}"))


def _get_client(db: Session, client_id: int) -> Subscription:
    client = db.get(Subscription, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="client_not_found")
    return client


def _out(db: Session, client: Subscription) -> ClientOut:
    plan = db.get(Plan, client.plan_id)
    target = db.get(User, client.user_id)
    return ClientOut(
        id=client.id,
        user_id=client.user_id,
        username=target.username if target else "",
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


def _ensure_owner(user: User, client: Subscription) -> None:
    if user.role == "RESELLER" and client.user_id != user.id:
        raise HTTPException(status_code=403, detail="forbidden")


def _ensure_plan_capacity(db: Session, user_id: int, plan: Plan, exclude_id: int | None = None) -> None:
    if exclude_id is None:
        count = db.scalar(select(Subscription.id).where(Subscription.user_id == user_id, Subscription.enabled.is_(True)))
    else:
        count = db.scalar(select(Subscription.id).where(Subscription.user_id == user_id, Subscription.enabled.is_(True), Subscription.id != exclude_id))
    if count is not None:
        # max_devices is a per-user active client limit.
        active_count = db.query(Subscription.id).filter(Subscription.user_id == user_id, Subscription.enabled.is_(True), *( [Subscription.id != exclude_id] if exclude_id is not None else [] )).count()
        if active_count >= plan.max_devices:
            raise HTTPException(status_code=409, detail="max_devices_reached")


def _ensure_not_expired(client: Subscription, plan: Plan | None) -> None:
    if not client.enabled:
        raise HTTPException(status_code=409, detail="client_disabled")
    if client.expires_at <= utcnow():
        raise HTTPException(status_code=409, detail="client_expired")
    quota = max(float(plan.quota_gb if plan else 0), 0.0)
    used = max(float(client.used_gb or 0), 0.0)
    if quota > 0 and used >= quota:
        raise HTTPException(status_code=409, detail="traffic_quota_exceeded")


@router.get("", response_model=list[ClientOut])
def list_clients(
    search: str = "",
    enabled: bool | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER")),
) -> list[ClientOut]:
    limit = min(max(limit, 1), 500)
    query = select(Subscription).order_by(Subscription.id.desc()).limit(limit)
    if user.role == "RESELLER":
        query = query.where(Subscription.user_id == user.id)
    if enabled is not None:
        query = query.where(Subscription.enabled.is_(enabled))
    if search.strip():
        query = query.join(User, User.id == Subscription.user_id).where(User.username.ilike(f"%{search.strip()}%"))
    return [_out(db, client) for client in db.scalars(query).all()]


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
    if payload.single_active and db.scalar(select(Subscription.id).where(Subscription.user_id == target.id, Subscription.enabled.is_(True))):
        raise HTTPException(status_code=409, detail="active_client_exists")
    if not payload.single_active:
        _ensure_plan_capacity(db, target.id, plan)
    node_keys = list(dict.fromkeys(key.strip().upper() for key in payload.node_keys if key.strip()))
    if len(node_keys) > 20:
        raise HTTPException(status_code=422, detail="too_many_nodes")
    expires_at = payload.expires_at or (utcnow() + timedelta(days=plan.duration_days))
    if expires_at <= utcnow():
        raise HTTPException(status_code=422, detail="expires_at_must_be_future")
    token = random_token(48)
    client = Subscription(user_id=target.id, plan_id=plan.id, token_hash=token_hash(token), node_keys=node_keys, enabled=True, used_gb=0, expires_at=expires_at)
    db.add(client)
    db.flush()
    record(db, user, "client.create", "client", str(client.id), request_ip(request), {"user_id": target.id, "plan_id": plan.id, "expires_at": expires_at.isoformat()})
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
    _ensure_owner(user, client)
    if payload.plan_id is not None:
        plan = db.get(Plan, payload.plan_id)
        if not plan or not plan.enabled:
            raise HTTPException(status_code=404, detail="plan_not_found")
        if client.enabled and plan.max_devices > 0:
            _ensure_plan_capacity(db, client.user_id, plan, exclude_id=client.id)
        client.plan_id = plan.id
    if payload.node_keys is not None:
        keys = list(dict.fromkeys(key.strip().upper() for key in payload.node_keys if key.strip()))
        if len(keys) > 20:
            raise HTTPException(status_code=422, detail="too_many_nodes")
        client.node_keys = keys
    if payload.enabled is not None:
        if payload.enabled:
            plan = db.get(Plan, client.plan_id)
            _ensure_plan_capacity(db, client.user_id, plan, exclude_id=client.id)
            if client.expires_at <= utcnow():
                raise HTTPException(status_code=422, detail="expires_at_must_be_future")
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
    _ensure_owner(user, client)
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
    _ensure_owner(user, client)
    record(db, user, "client.delete", "client", str(client.id), request_ip(request))
    db.delete(client)
    db.commit()
    return {"ok": True}
