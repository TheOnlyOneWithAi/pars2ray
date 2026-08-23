from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import decrypt_secret, encrypt_secret
from app.db.base import get_db
from app.models.entities import SystemSetting, User
from app.schemas import PanelDomainUpdate, SystemSettingUpdate
from app.services.audit import record
from app.services.panel_proxy import apply_proxy

router = APIRouter(prefix="/api/v1/system", tags=["system"])

PANEL_DOMAIN_KEY = "panel.domain"
PANEL_TLS_KEY = "panel.tls"
PANEL_EMAIL_KEY = "panel.email"
SUBSCRIPTION_HTML_KEY = "subscription.page_html"
DEFAULT_SUBSCRIPTION_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}}</title></head>
<body>
<h1>{{title}}</h1>
<p>User: {{username}}</p>
<p>Expires: {{expires_at}}</p>
<p>Traffic: {{used_gb}} / {{quota_gb}} GB ({{remaining_percent}}% remaining)</p>
<div>{{vless_links}}</div>
<div>{{connection_instructions}}</div>
</body>
</html>"""


def admin_user():
    return Depends(require_roles("SUPER_ADMIN", "ADMIN"))


def super_admin_user():
    return Depends(require_roles("SUPER_ADMIN"))


def _read(db: Session, key: str, default: str = "") -> str:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not row or not row.value_enc:
        return default
    try:
        return decrypt_secret(row.value_enc)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="system_setting_decryption_failed") from exc


def _write(db: Session, key: str, value: str, *, is_secret: bool = False) -> None:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not row:
        db.add(SystemSetting(key=key, value_enc=encrypt_secret(value), is_secret=is_secret))
    else:
        row.value_enc = encrypt_secret(value)
        row.is_secret = is_secret


@router.get("/panel-domain")
def panel_domain(db: Session = Depends(get_db), user: User = admin_user()) -> dict:
    return {
        "domain": _read(db, PANEL_DOMAIN_KEY),
        "tls": _read(db, PANEL_TLS_KEY, "true").lower() == "true",
        "email": _read(db, PANEL_EMAIL_KEY),
    }


@router.put("/panel-domain")
def update_panel_domain(payload: PanelDomainUpdate, request: Request, db: Session = Depends(get_db), user: User = super_admin_user()) -> dict:
    try:
        result = apply_proxy(payload.domain, payload.tls, payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result)
    _write(db, PANEL_DOMAIN_KEY, result["domain"])
    _write(db, PANEL_TLS_KEY, "true" if payload.tls else "false")
    _write(db, PANEL_EMAIL_KEY, payload.email or "")
    record(db, user, "system.panel_domain.update", "system_setting", PANEL_DOMAIN_KEY, request.client.host if request.client else "")
    db.commit()
    return result


@router.get("/subscription-html")
def subscription_html(db: Session = Depends(get_db), user: User = admin_user()) -> dict:
    return {"html": _read(db, SUBSCRIPTION_HTML_KEY, DEFAULT_SUBSCRIPTION_HTML)}


@router.put("/subscription-html")
def update_subscription_html(payload: SystemSettingUpdate, request: Request, db: Session = Depends(get_db), user: User = super_admin_user()) -> dict:
    if not payload.value.strip():
        raise HTTPException(status_code=422, detail="subscription_html_required")
    _write(db, SUBSCRIPTION_HTML_KEY, payload.value, is_secret=False)
    record(db, user, "system.subscription_html.update", "system_setting", SUBSCRIPTION_HTML_KEY, request.client.host if request.client else "")
    db.commit()
    return {"ok": True}
