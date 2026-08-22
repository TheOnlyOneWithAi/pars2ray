from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import request_ip, require_roles
from app.core.security import hash_password, random_token, token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Plan, Role, Subscription, User
from app.schemas import UserCreate, UserOut
from app.services.audit import record

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.post("/users", response_model=UserOut, tags=["users"])
def create_user_with_subscription(
    payload: UserCreate,
    request: Request,
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
    if payload.role == "USER" and payload.plan_id is None:
        raise HTTPException(status_code=422, detail="plan_required_for_user")
    plan = db.get(Plan, payload.plan_id) if payload.plan_id is not None else None
    if payload.plan_id is not None and (not plan or not plan.enabled):
        raise HTTPException(status_code=404, detail="plan_not_found")

    node_keys = list(dict.fromkeys(key.strip().upper() for key in payload.node_keys if key.strip()))
    if len(node_keys) > 20:
        raise HTTPException(status_code=422, detail="too_many_nodes")
    if node_keys:
        from app.models.entities import Node
        known = set(db.scalars(select(Node.node_key).where(Node.node_key.in_(node_keys))).all())
        missing = sorted(set(node_keys) - known)
        if missing:
            raise HTTPException(status_code=422, detail={"code": "unknown_nodes", "nodes": missing})

    expires_at = None
    raw_token = None
    if plan is not None:
        expires_at = payload.expires_at or (utcnow() + timedelta(days=plan.duration_days))
        if expires_at <= utcnow():
            raise HTTPException(status_code=422, detail="expires_at_must_be_future")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        roles=[role_row],
    )
    db.add(user)
    db.flush()

    if plan is not None:
        raw_token = random_token(48)
        db.add(Subscription(
            user_id=user.id,
            plan_id=plan.id,
            token_hash=token_hash(raw_token),
            node_keys=node_keys,
            enabled=True,
            used_gb=0,
            expires_at=expires_at,
        ))

    record(db, actor, "user.create", "user", str(user.id), request_ip(request), {
        "role": payload.role,
        "plan_id": plan.id if plan else None,
        "subscription_created": plan is not None,
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
        quota_gb=float(plan.quota_gb) if plan else None,
        used_gb=0.0 if plan else None,
        expires_at=expires_at,
        subscription_token=raw_token,
    )
