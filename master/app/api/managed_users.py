from __future__ import annotations

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import encrypt_secret, hash_password, random_token, token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Node, Role, Subscription, User
from app.services.audit import record

router = APIRouter(prefix="/api/v1/users/managed", tags=["users"])

class ManagedUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str | None = Field(default=None, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(default="USER", pattern=r"^(SUPER_ADMIN|ADMIN|OPERATOR|RESELLER|USER)$")
    is_active: bool = True
    quota_gb: float = Field(default=0, ge=0)
    duration_days: int = Field(default=0, ge=0, le=36500)
    expires_at: object | None = None
    node_keys: list[str] = Field(default_factory=list, max_length=20)

class ManagedUserUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=254)
    is_active: bool | None = None
    quota_gb: float | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, ge=0, le=36500)
    expires_at: object | None = None
    node_keys: list[str] | None = Field(default=None, max_length=20)


def _expiry(payload: ManagedUserCreate | ManagedUserUpdate, current=None):
    if payload.expires_at is not None:
        return payload.expires_at
    days = getattr(payload, "duration_days", None)
    if days is not None:
        return None if days == 0 else utcnow() + timedelta(days=days)
    return current


def _nodes(db: Session, keys: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(key.strip().upper() for key in keys if key.strip()))
    if len(normalized) > 20:
        raise HTTPException(status_code=422, detail="too_many_nodes")
    if not normalized:
        return []
    known = set(db.scalars(select(Node.node_key).where(Node.node_key.in_(normalized))).all())
    missing = sorted(set(normalized) - known)
    if missing:
        raise HTTPException(status_code=422, detail={"code": "unknown_nodes", "nodes": missing})
    return normalized


def _out(user: User, sub: Subscription | None) -> dict:
    return {"id": user.id, "username": user.username, "email": user.email, "role": user.role, "is_active": user.is_active, "quota_gb": float(user.quota_gb or 0), "used_gb": float(user.used_gb or 0), "expires_at": user.expires_at, "unlimited_quota": float(user.quota_gb or 0) == 0, "unlimited_time": user.expires_at is None, "subscription_id": sub.id if sub else None, "subscription_token": decrypt_token(sub) if sub else None, "node_keys": list(sub.node_keys or []) if sub else []}


def decrypt_token(sub: Subscription) -> str | None:
    if not sub.token_enc:
        return None
    from app.core.security import decrypt_secret
    return decrypt_secret(sub.token_enc)

@router.post("", status_code=201)
def create_user(payload: ManagedUserCreate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("SUPER_ADMIN", "ADMIN"))) -> dict:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="username_exists")
    if payload.email and db.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="email_exists")
    role = db.scalar(select(Role).where(Role.name == payload.role))
    if not role:
        raise HTTPException(status_code=422, detail="role_not_found")
    expiry = _expiry(payload)
    if expiry is not None and expiry <= utcnow():
        raise HTTPException(status_code=422, detail="expires_at_must_be_future")
    keys = _nodes(db, payload.node_keys)
    user = User(username=payload.username, email=payload.email, password_hash=hash_password(payload.password), is_active=payload.is_active, quota_gb=payload.quota_gb, used_gb=0, expires_at=expiry, roles=[role])
    db.add(user)
    db.flush()
    raw = random_token(48)
    sub = Subscription(user_id=user.id, plan_id=None, token_hash=token_hash(raw), token_enc=encrypt_secret(raw), node_keys=keys, enabled=True, used_gb=0, expires_at=expiry)
    db.add(sub)
    record(db, actor, "user.managed.create", "user", str(user.id), request.client.host if request.client else "", {"quota_gb": payload.quota_gb, "unlimited_quota": payload.quota_gb == 0, "unlimited_time": expiry is None, "node_count": len(keys)})
    db.commit()
    db.refresh(user)
    return _out(user, sub)

@router.get("")
def list_users(db: Session = Depends(get_db), actor: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR", "RESELLER"))) -> list[dict]:
    rows = db.execute(select(User, Subscription).outerjoin(Subscription, Subscription.user_id == User.id).order_by(User.id.desc())).all()
    return [_out(user, sub) for user, sub in rows]

@router.patch("/{user_id}")
def update_user(user_id: int, payload: ManagedUserUpdate, request: Request, db: Session = Depends(get_db), actor: User = Depends(require_roles("SUPER_ADMIN", "ADMIN"))) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    if payload.email is not None:
        user.email = payload.email
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.quota_gb is not None:
        user.quota_gb = payload.quota_gb
    expiry = _expiry(payload, user.expires_at)
    if payload.duration_days is not None or payload.expires_at is not None:
        user.expires_at = expiry
    sub = db.scalar(select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.id.desc()))
    if not sub:
        raw = random_token(48)
        sub = Subscription(user_id=user.id, plan_id=None, token_hash=token_hash(raw), token_enc=encrypt_secret(raw), node_keys=[], enabled=True, used_gb=user.used_gb, expires_at=user.expires_at)
        db.add(sub)
    else:
        sub.expires_at = user.expires_at
        sub.used_gb = user.used_gb
    if payload.node_keys is not None:
        sub.node_keys = _nodes(db, payload.node_keys)
    record(db, actor, "user.managed.update", "user", str(user.id), request.client.host if request.client else "")
    db.commit()
    db.refresh(user)
    return _out(user, sub)
