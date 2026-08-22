from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import request_ip, require_roles
from app.api.subscription_server import _public_subscription_base, _subscription_path
from app.core.security import encrypt_secret, hash_password, random_token, token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Node, Plan, Role, Subscription, User
from app.schemas import UserCreate, UserUpdate
from app.services.audit import record
from app.services.inbound_store import ensure_tables, list_inbounds

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.post("/users", tags=["users"])
def create_user_with_subscription(payload: UserCreate, request: Request, quota_gb: float | None = Query(default=None, ge=0), duration_days: int | None = Query(default=None, ge=0, le=36500), db: Session = Depends(get_db), actor: User = Depends(require_roles("SUPER_ADMIN", "ADMIN"))) -> dict:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="username_exists")
    if payload.email and db.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="email_exists")
    role_row = db.scalar(select(Role).where(Role.name == payload.role))
    if not role_row:
        raise HTTPException(status_code=422, detail="role_not_found")
    plan = db.get(Plan, payload.plan_id) if payload.plan_id is not None else None
    if payload.plan_id is not None and (not plan or not plan.enabled):
        raise HTTPException(status_code=404, detail="plan_not_found")

    inbound_ids = list(dict.fromkeys(int(item) for item in payload.inbound_ids))
    available: dict[int, dict] = {}
    if inbound_ids:
        ensure_tables(db.get_bind())
        available = {int(row["id"]): row for row in list_inbounds(db)}
        missing = sorted(set(inbound_ids) - set(available))
        if missing:
            raise HTTPException(status_code=422, detail={"code": "unknown_inbounds", "inbounds": missing})

    node_keys = list(dict.fromkeys(key.strip().upper() for key in payload.node_keys if key.strip()))
    if inbound_ids:
        inbound_nodes = {str(available[item]["node_key"]).strip().upper() for item in inbound_ids}
        node_keys = list(dict.fromkeys(node_keys + sorted(inbound_nodes)))
    if len(node_keys) > 20:
        raise HTTPException(status_code=422, detail="too_many_nodes")
    if node_keys:
        known = set(db.scalars(select(Node.node_key).where(Node.node_key.in_(node_keys))).all())
        missing = sorted(set(node_keys) - known)
        if missing:
            raise HTTPException(status_code=422, detail={"code": "unknown_nodes", "nodes": missing})

    effective_quota = float(quota_gb if quota_gb is not None else (payload.quota_gb if payload.plan_id is None else plan.quota_gb if plan else 0))
    effective_duration = duration_days if duration_days is not None else (payload.duration_days if payload.plan_id is None else plan.duration_days if plan else 0)
    expires_at = payload.expires_at
    if expires_at is None and effective_duration > 0:
        expires_at = utcnow() + timedelta(days=effective_duration)
    if expires_at is not None and expires_at <= utcnow():
        raise HTTPException(status_code=422, detail="expires_at_must_be_future")

    generated_password = random_token(32)
    user = User(username=payload.username, email=payload.email, password_hash=hash_password(payload.password or generated_password), is_active=payload.is_active, quota_gb=effective_quota, used_gb=0, expires_at=expires_at, roles=[role_row])
    db.add(user)
    db.flush()

    raw_token = random_token(48)
    subscription_config = json.dumps({"inbound_ids": inbound_ids}, separators=(",", ":"))
    subscription = Subscription(user_id=user.id, plan_id=plan.id if plan else None, token_hash=token_hash(raw_token), token_enc=encrypt_secret(raw_token), config_enc=encrypt_secret(subscription_config), node_keys=node_keys, enabled=True, used_gb=0, expires_at=expires_at)
    db.add(subscription)
    db.flush()

    record(db, actor, "user.create", "user", str(user.id), request_ip(request), {"role": payload.role, "plan_id": plan.id if plan else None, "quota_gb": effective_quota, "duration_days": effective_duration, "unlimited_quota": effective_quota == 0, "unlimited_time": expires_at is None, "node_count": len(node_keys), "inbound_count": len(inbound_ids)})
    db.commit()
    db.refresh(user)

    base = _public_subscription_base(request, db)
    origin = base.split(_subscription_path(db), 1)[0]
    subscription_url = f"{origin}/s/{quote(raw_token, safe='')}"
    return {"id": user.id, "username": user.username, "email": user.email, "role": user.role, "is_active": user.is_active, "created_at": user.created_at, "last_login_at": user.last_login_at, "plan_id": plan.id if plan else None, "quota_gb": float(user.quota_gb), "used_gb": float(user.used_gb), "expires_at": user.expires_at, "subscription_url": subscription_url, "raw_subscription_url": f"{subscription_url}/raw", "inbound_required": False, "inbound_count": len(inbound_ids)}


@router.patch("/users/{user_id}/limits", tags=["users"])
def update_user_limits(user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("SUPER_ADMIN", "ADMIN"))) -> dict:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user_not_found")
    if payload.quota_gb is not None:
        target.quota_gb = float(payload.quota_gb)
    if payload.duration_days is not None:
        target.expires_at = utcnow() + timedelta(days=payload.duration_days) if payload.duration_days > 0 else None
    elif payload.expires_at is not None:
        if payload.expires_at <= utcnow():
            raise HTTPException(status_code=422, detail="expires_at_must_be_future")
        target.expires_at = payload.expires_at

    # Plan-less subscriptions inherit the user's direct entitlement. Keep their
    # mirrored expiry synchronized so an old subscription value cannot override it.
    for sub in db.scalars(select(Subscription).where(Subscription.user_id == target.id, Subscription.plan_id.is_(None), Subscription.enabled.is_(True))).all():
        sub.expires_at = target.expires_at

    record(db, actor, "user.limits.update", "user", str(target.id), request_ip(request), {"quota_gb": float(target.quota_gb or 0), "expires_at": target.expires_at.isoformat() if target.expires_at else None, "unlimited_quota": float(target.quota_gb or 0) == 0, "unlimited_time": target.expires_at is None})
    db.commit()
    db.refresh(target)
    return {"id": target.id, "username": target.username, "quota_gb": float(target.quota_gb or 0), "used_gb": float(target.used_gb or 0), "expires_at": target.expires_at, "unlimited_quota": float(target.quota_gb or 0) == 0, "unlimited_time": target.expires_at is None}
