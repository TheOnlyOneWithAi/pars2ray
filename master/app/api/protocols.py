from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_roles
from app.core.security import token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Node, Route, Subscription, SystemSetting, User
from app.schemas import ConfigBuildRequest, PanelDomainUpdate
from app.services import agent_client
from app.services.config_builder import build_config
from app.services.panel_proxy import apply_proxy

router = APIRouter(prefix="/api/v1", tags=["protocols"])


def _setting(db: Session, key: str, default: str = "") -> str:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not row:
        return default
    from app.core.security import decrypt_secret
    try:
        return decrypt_secret(row.value_enc)
    except Exception:
        return default


def _client_id(token_hash_value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pars2ray:{token_hash_value}"))


def _subscription_rows(db: Session, token: str) -> tuple[Subscription, User] | None:
    sub = db.scalar(select(Subscription).where(Subscription.token_hash == token_hash(token)))
    if not sub or not sub.enabled or sub.expires_at <= utcnow():
        return None
    user = db.get(User, sub.user_id)
    if not user or not user.is_active:
        return None
    return sub, user


def _template(db: Session) -> str:
    return _setting(db, "subscription.html", """<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{{title}}</title><style>body{font-family:system-ui;background:#0b1020;color:#fff;max-width:900px;margin:40px auto;padding:20px}a{color:#7dd3fc}pre{white-space:pre-wrap;background:#151b2e;padding:16px;border-radius:12px}</style></head><body><h1>{{title}}</h1><p>User: {{username}}</p><p>Expires: {{expires_at}}</p><h2>Configurations</h2><pre>{{configs}}</pre></body></html>""")


def _render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def _routes_for_subscription(db: Session, sub: Subscription) -> list[Route]:
    routes = db.scalars(select(Route).where(Route.is_active.is_(True)).order_by(Route.id)).all()
    allowed = set(sub.node_keys)
    return [route for route in routes if not allowed or allowed.intersection(route.node_keys)]


def _connection_lines(db: Session, sub: Subscription, token: str) -> list[str]:
    lines: list[str] = []
    client_id = _client_id(token_hash(token))
    for route in _routes_for_subscription(db, sub):
        cfg = route.config_enc
        # Route config is intentionally stored encrypted; public subscription output
        # uses the safe public fields on Route and the panel/node endpoint fallback.
        server = ""
        try:
            from app.core.security import decrypt_secret
            raw = decrypt_secret(cfg) if cfg else ""
            data = json.loads(raw) if raw else {}
            server = str(data.get("server") or data.get("host") or "")
        except Exception:
            data = {}
        if not server:
            node = db.scalar(select(Node).where(Node.node_key == route.node_keys[0])) if route.node_keys else None
            server = (node.endpoint.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0] if node else "")
        port = int(data.get("port", 443)) if isinstance(data, dict) else 443
        name = quote(route.name, safe="")
        if route.protocol == "vless":
            lines.append(f"vless://{client_id}@{server}:{port}?type={quote(route.transport)}&security={'tls' if data.get('tls') else 'none'}#{name}")
        elif route.protocol == "vmess":
            payload = {"v":"2","ps":route.name,"add":server,"port":str(port),"id":client_id,"aid":"0","net":route.transport,"tls":"tls" if data.get('tls') else ""}
            lines.append("vmess://" + base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=") )
        elif route.protocol == "trojan":
            lines.append(f"trojan://{client_id}@{server}:{port}?security={'tls' if data.get('tls') else 'none'}&type={quote(route.transport)}#{name}")
        elif route.protocol == "hysteria2":
            lines.append(f"hysteria2://{client_id}@{server}:{port}/?sni={quote(str(data.get('server_name') or server))}#{name}")
        elif route.protocol == "shadowsocks":
            method = str(data.get("method", "2022-blake3-aes-128-gcm"))
            userinfo = base64.urlsafe_b64encode(f"{method}:{client_id}".encode()).decode().rstrip("=")
            lines.append(f"ss://{userinfo}@{server}:{port}#{name}")
    return lines


@router.post("/routes/{route_id}/build-config")
async def build_route_config(route_id: int, payload: ConfigBuildRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))) -> dict:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="route_not_found")
    clients = payload.clients
    if not clients:
        subs = db.scalars(select(Subscription).where(Subscription.enabled.is_(True), Subscription.expires_at > utcnow())).all()
        clients = [{"id": _client_id(sub.token_hash), "email": f"sub-{sub.id}"} for sub in subs if not sub.node_keys or set(sub.node_keys).intersection(route.node_keys)]
    try:
        config = build_config({"name": route.name, "core": route.core, "protocol": route.protocol, "transport": route.transport, "config": _decrypt_route_config(route)}, clients)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    applied: list[str] = []
    if payload.apply:
        for key in route.node_keys:
            node = db.scalar(select(Node).where(Node.node_key == key))
            if not node:
                continue
            result = await agent_client.apply_config(node, {"core": route.core, "config": config, "candidate_id": f"route-{route.id}"})
            if not result.get("ok"):
                raise HTTPException(status_code=502, detail={"node": key, "reason": result.get("reason", "apply_failed")})
            applied.append(key)
    return {"ok": True, "route_id": route.id, "core": route.core, "protocol": route.protocol, "transport": route.transport, "config": config, "applied_nodes": applied}


def _decrypt_route_config(route: Route) -> dict:
    if not route.config_enc:
        return {}
    try:
        from app.core.security import decrypt_secret
        return json.loads(decrypt_secret(route.config_enc))
    except Exception:
        return {}


@router.get("/system/panel-domain")
def panel_domain(db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN"))) -> dict:
    return {"domain": _setting(db, "panel.domain"), "tls": _setting(db, "panel.tls", "false").lower() == "true", "email": _setting(db, "panel.tls.email")}


@router.put("/system/panel-domain")
def update_panel_domain(payload: PanelDomainUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN"))) -> dict:
    try:
        result = apply_proxy(payload.domain, payload.tls, payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result)
    from app.core.security import encrypt_secret
    values = {"panel.domain": payload.domain.strip().lower().rstrip("."), "panel.tls": str(payload.tls).lower(), "panel.tls.email": payload.email or ""}
    for key, value in values.items():
        row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if not row:
            db.add(SystemSetting(key=key, value_enc=encrypt_secret(value), is_secret=False))
        else:
            row.value_enc = encrypt_secret(value)
    db.commit()
    return result


@router.put("/system/subscription-html")
def update_subscription_html(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN"))) -> dict:
    template = payload.get("html")
    if not isinstance(template, str) or not template.strip():
        raise HTTPException(status_code=422, detail="html_required")
    if len(template) > 100000:
        raise HTTPException(status_code=413, detail="html_too_large")
    from app.core.security import encrypt_secret
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == "subscription.html"))
    if not row:
        db.add(SystemSetting(key="subscription.html", value_enc=encrypt_secret(template), is_secret=False))
    else:
        row.value_enc = encrypt_secret(template)
    db.commit()
    return {"ok": True, "bytes": len(template.encode("utf-8"))}


@router.get("/system/subscription-html")
def get_subscription_html(db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN"))) -> dict:
    return {"html": _template(db)}


@router.get("/sub/{token}", response_class=HTMLResponse, include_in_schema=False)
def subscription_page(token: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    found = _subscription_rows(db, token)
    if not found:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    sub, user = found
    lines = _connection_lines(db, sub, token)
    title = _setting(db, "subscription.title", "Pars2Ray Subscription")
    template = _template(db)
    values = {
        "title": html.escape(title),
        "username": html.escape(user.username),
        "expires_at": html.escape(sub.expires_at.isoformat()),
        "token": html.escape(token),
        "subscription_url": html.escape(str(request.url)),
        "configs": html.escape("\n".join(lines)),
        "config_count": str(len(lines)),
    }
    return HTMLResponse(_render(template, values))


@router.get("/sub/{token}/raw", response_class=PlainTextResponse, include_in_schema=False)
def subscription_raw(token: str, db: Session = Depends(get_db)) -> PlainTextResponse:
    found = _subscription_rows(db, token)
    if not found:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    sub, _ = found
    return PlainTextResponse("\n".join(_connection_lines(db, sub, token)), media_type="text/plain")
