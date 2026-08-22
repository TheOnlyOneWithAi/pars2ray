from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.subscription_server import _all_links, _headers, _public_subscription_base, _subscription_rows, subscription
from app.core.security import token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Subscription, User

public_router = APIRouter(tags=["secure-subscriptions"])


def _lookup(token: str, db: Session) -> tuple[Subscription, User]:
    if len(token) < 32 or len(token) > 128:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    sub = db.scalar(select(Subscription).where(Subscription.token_hash == token_hash(token), Subscription.enabled.is_(True)))
    if not sub:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    user = db.get(User, sub.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    expires_at = sub.expires_at or user.expires_at
    if expires_at is not None and expires_at <= utcnow():
        raise HTTPException(status_code=404, detail="subscription_not_found")
    quota = max(float(user.quota_gb or 0), 0.0)
    used = max(float(user.used_gb or sub.used_gb or 0), 0.0)
    if quota > 0 and used >= quota:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    return sub, user


def _secure_url(request: Request, db: Session, token: str) -> str:
    return f"{_public_subscription_base(request, db)}s/{quote(token, safe='')}"


@public_router.get("/s/{token}")
def secure_subscription(token: str, request: Request, db: Session = Depends(get_db)) -> Response:
    sub, user = _lookup(token, db)
    response = subscription(user.username, request, db)
    secure = _secure_url(request, db, token)
    legacy = f"{_public_subscription_base(request, db)}{quote(user.username, safe='')}"
    if hasattr(response, "body") and response.body:
        body = response.body.replace(legacy.encode(), secure.encode())
        response.body = body
        response.headers["content-length"] = str(len(body))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@public_router.get("/s/{token}/raw")
def secure_subscription_raw(token: str, db: Session = Depends(get_db)) -> PlainTextResponse:
    sub, user = _lookup(token, db)
    body = "\n".join(_all_links(db, sub, user))
    response = PlainTextResponse(body, headers=_headers(db, user, sub))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
