from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, token_hash
from app.db.base import get_db
from app.models.entities import ApiKey, User


def bearer_value(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip()


def current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if x_api_key:
        key = db.scalar(select(ApiKey).where(ApiKey.key_hash == token_hash(x_api_key), ApiKey.revoked_at.is_(None)))
        if key:
            user = db.get(User, key.user_id)
            if user and user.is_active:
                key.last_used_at = __import__("datetime").datetime.utcnow()
                db.commit()
                return user
    token = bearer_value(authorization)
    claims = decode_access_token(token) if token else None
    if not claims or not claims.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    user = db.scalar(select(User).where(User.username == claims["sub"], User.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_role")
        return user

    return dependency


def request_ip(request: Request) -> str:
    return (request.client.host if request.client else "unknown")[:64]
