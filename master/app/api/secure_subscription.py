from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.subscription_server import _all_links, _headers, _public_subscription_base, _subscription_path, subscription, subscription_raw
from app.core.security import token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Plan, Subscription, User

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
    expires_at = sub.expires_at if sub.expires_at is not None else user.expires_at
    if expires_at is not None and expires_at <= utcnow():
        raise HTTPException(status_code=404, detail="subscription_not_found")
    plan = db.get(Plan, sub.plan_id) if sub.plan_id is not None else None
    quota = max(float(plan.quota_gb if plan is not None else user.quota_gb or 0), 0.0)
    used = max(float(user.used_gb or 0), float(sub.used_gb or 0), 0.0)
    if quota > 0 and used >= quota:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    return sub, user


def _secure_url(request: Request, db: Session, token: str) -> str:
    base = _public_subscription_base(request, db)
    path = _subscription_path(db)
    origin = base[:-len(path)] if base.endswith(path) else f"{request.url.scheme}://{request.headers.get('host') or request.url.netloc}"
    return f"{origin}/s/{quote(token, safe='')}"


def _rewrite_subscription_url(response: Response, old_url: str, new_url: str) -> None:
    body = getattr(response, "body", None)
    if isinstance(body, bytes) and body:
        response.body = body.replace(old_url.encode(), new_url.encode())
        response.headers["content-length"] = str(len(response.body))


@public_router.get("/s/{token}")
def secure_subscription(token: str, request: Request, db: Session = Depends(get_db)) -> Response:
    sub, user = _lookup(token, db)
    response = subscription(user.username, request, db)
    secure = _secure_url(request, db, token)
    legacy = f"{_public_subscription_base(request, db)}{quote(user.username, safe='')}"
    _rewrite_subscription_url(response, legacy, secure)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@public_router.get("/s/{token}/raw")
def secure_subscription_raw(token: str, db: Session = Depends(get_db)) -> PlainTextResponse:
    sub, user = _lookup(token, db)
    response = PlainTextResponse("\n".join(_all_links(db, sub, user)), headers=_headers(db, user, sub), media_type="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@public_router.get("/link/{value}")
def compatibility_subscription(value: str, request: Request, db: Session = Depends(get_db)) -> Response:
    try:
        sub, user = _lookup(value, db)
    except HTTPException:
        return subscription(value, request, db)
    response = subscription(user.username, request, db)
    _rewrite_subscription_url(response, f"{_public_subscription_base(request, db)}{quote(user.username, safe='')}", _secure_url(request, db, value))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@public_router.get("/link/{value}/raw")
def compatibility_subscription_raw(value: str, request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    try:
        sub, user = _lookup(value, db)
    except HTTPException:
        return subscription_raw(value, request, db)
    response = PlainTextResponse("\n".join(_all_links(db, sub, user)), headers=_headers(db, user, sub), media_type="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
