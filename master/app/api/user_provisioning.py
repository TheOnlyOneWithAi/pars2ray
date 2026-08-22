from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import request_ip, require_roles
from app.core.security import encrypt_secret, hash_password, random_token, token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Node, Plan, Role, Subscription, User
from app.schemas import UserCreate, UserOut
from app.services.audit import record

router = APIRouter(prefix="/api/v1", tags=["users"])

@router.post("/users", response_model=UserOut, tags=["users"])
def create_user_with_subscription(
    payload: UserCreate,
    request: Request,
    quota_gb: float | None = Query(default=None, ge=0),
    duration_days: int | None = Query(default=None, ge=0, le=36500),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("SUPER_ADMIN", "ADMIN")),
) -> UserOut:
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

    node_keys = list(dict.fromkeys(key.strip().upper() for key in payload.node_keys if key.strip()))
    if len(node_keys) > 20:
        raise HTTPException(status_code=422, detail="too_many_nodes")
    if node_keys:
        known = set(db.scalars(select(Node.node_key).where(Node.node_key.in_(node_keys))).all())
        missing = sorted(set(node_keys) - known)
        if missing:
            raise HTTPException(status_code=422, detail={"code": "unknown_nodes", "nodes": missing})

    effective_quota = float(quota_gb if quota_gb is not None else (plan.quota_gb if plan else 0))
    effective_duration = duration_days if duration_days is not None else (plan.duration_days if plan else 0)
    expires_at = payload.expires_at
    if expires_at is None and effective_duration > 0:
        expires_at = utcnow() + timedelta(days=effective_duration)
    if expires_at is not None and expires_at <= utcnow():
        raise HTTPException(status_code=422, detail="expires_at_must_be_future")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        quota_gb=effective_quota,
        used_gb=0,
        expires_at=expires_at,
        roles=[role_row],
    )
    db.add(user)
    db.flush()

    raw_token = random_token(48)
    db.add(Subscription(
        user_id=user.id,
        plan_id=plan.id if plan else None,
        token_hash=token_hash(raw_token),
        token_enc=encrypt_secret(raw_token),
        node_keys=node_keys,
        enabled=True,
        used_gb=0,
        expires_at=expires_at,
    ))

    record(db, actor, "user.create", "user", str(user.id), request_ip(request), {
        "role": payload.role,
        "plan_id": plan.id if plan else None,
        "quota_gb": effective_quota,
        "duration_days": effective_duration,
        "unlimited_quota": effective_quota == 0,
        "unlimited_time": expires_at is None,
        "node_count": len(node_keys),
    })
    db.commit()
    db.refresh(user)
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        plan_id=plan.id if plan else None,
        quota_gb=float(user.quota_gb),
        used_gb=float(user.used_gb),
        expires_at=user.expires_at,
        subscription_token=raw_token,
    )
