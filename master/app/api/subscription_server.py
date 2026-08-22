from __future__ import annotations

import base64
import html
import json
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_roles
from app.core.security import decrypt_secret, encrypt_secret, random_token, token_hash, utcnow
from app.db.base import get_db
from app.models.entities import Node, Plan, Route, Subscription, SystemSetting, User

router = APIRouter(prefix="/api/v1", tags=["subscriptions"])
public_router = APIRouter(tags=["subscriptions"])


def _setting(db: Session, key: str, default: str = "") -> str:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not row:
        return default
    try:
        return decrypt_secret(row.value_enc)
    except Exception:
        return default


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row:
        row.value_enc = encrypt_secret(value)
    else:
        db.add(SystemSetting(key=key, value_enc=encrypt_secret(value), is_secret=False))


def _subscription_path(db: Session) -> str:
    path = _setting(db, "subscription.path", "/link/").strip()
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def _public_subscription_base(request: Request, db: Session) -> str:
    domain = _setting(db, "subscription.domain") or _setting(db, "panel.domain")
    scheme = _setting(db, "subscription.scheme")
    if not scheme:
        scheme = "https" if _setting(db, "panel.tls", "false").lower() == "true" else request.url.scheme
    port = int(_setting(db, "subscription.port", "2096") or 2096)
    if domain:
        host = domain.strip().lower().rstrip(".")
        port_part = "" if (scheme == "https" and port == 443) or (scheme == "http" and port == 80) else f":{port}"
        return f"{scheme}://{host}{port_part}{_subscription_path(db)}"
    host = request.headers.get("host") or request.url.netloc
    return f"{request.url.scheme}://{host}{_subscription_path(db)}"


def _subscription_rows(db: Session, token: str) -> tuple[Subscription, User] | None:
    sub = db.scalar(select(Subscription).where(Subscription.token_hash == token_hash(token)))
    if not sub or not sub.enabled:
        return None
    user = db.get(User, sub.user_id)
    if not user or not user.is_active:
        return None
    expires_at = sub.expires_at or user.expires_at
    if expires_at is not None and expires_at <= utcnow():
        return None
    quota_gb = max(float(user.quota_gb or 0), 0.0)
    used_gb = max(float(user.used_gb or sub.used_gb or 0), 0.0)
    if quota_gb > 0 and used_gb >= quota_gb:
        return None
    return sub, user


def _client_id(token: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pars2ray:client:{token_hash(token)}"))


def _route_links(db: Session, sub: Subscription, user: User, token: str) -> list[str]:
    rows: list[str] = []
    routes = db.scalars(select(Route).where(Route.is_active.is_(True)).order_by(Route.id)).all()
    allowed = set(sub.node_keys)
    client_id = _client_id(token)
    email = user.email or user.username
    for route in routes:
        if allowed and not allowed.intersection(route.node_keys):
            continue
        try:
            cfg = json.loads(decrypt_secret(route.config_enc)) if route.config_enc else {}
        except Exception:
            cfg = {}
        server = str(cfg.get("server") or cfg.get("host") or "")
        if not server and route.node_keys:
            node = db.scalar(select(Node).where(Node.node_key == route.node_keys[0]))
            if node:
                server = node.endpoint.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0]
        if not server:
            continue
        port = int(cfg.get("port", 443))
        name = quote(route.name, safe="")
        transport = route.transport
        security = str(cfg.get("security") or ("tls" if cfg.get("tls") else "none")).lower()
        params = {"type": "ws" if transport == "websocket" else transport, "security": security}
        if cfg.get("server_name") or cfg.get("sni"):
            params["sni"] = str(cfg.get("server_name") or cfg.get("sni"))
        if cfg.get("fingerprint"):
            params["fp"] = str(cfg["fingerprint"])
        reality = cfg.get("reality") or {}
        if security == "reality":
            if reality.get("public_key") or cfg.get("public_key"):
                params["pbk"] = str(reality.get("public_key") or cfg.get("public_key"))
            if reality.get("short_id") or cfg.get("short_id"):
                params["sid"] = str(reality.get("short_id") or cfg.get("short_id"))
        if transport in {"websocket", "httpupgrade", "xhttp"}:
            params["path"] = str(cfg.get("path", "/"))
            if cfg.get("host"):
                params["host"] = str(cfg["host"])
        if transport == "grpc":
            params["serviceName"] = str(cfg.get("service_name", "pars2ray"))
        query = "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in params.items())
        if route.protocol == "vless":
            rows.append(f"vless://{client_id}@{server}:{port}?{query}#{name}")
        elif route.protocol == "vmess":
            payload = {"v": "2", "ps": route.name, "add": server, "port": str(port), "id": client_id, "aid": "0", "scy": "auto", "net": transport, "type": "none", "host": str(cfg.get("host", "")), "path": str(cfg.get("path", "/")), "tls": "tls" if security == "tls" else "", "sni": str(cfg.get("server_name") or cfg.get("sni") or "")}
            rows.append("vmess://" + base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode())
        elif route.protocol == "shadowsocks":
            method = str(cfg.get("method", "aes-128-gcm"))
            password = str(cfg.get("password") or client_id)
            auth = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
            rows.append(f"ss://{auth}@{server}:{port}#{name}")
        elif route.protocol == "trojan":
            rows.append(f"trojan://{client_id}@{server}:{port}?{query}#{name}")
    return rows


def _stored_links(sub: Subscription) -> list[str]:
    if not sub.config_enc:
        return []
    try:
        data = json.loads(decrypt_secret(sub.config_enc))
    except Exception:
        return []
    links: list[str] = []
    if isinstance(data, dict):
        raw_links = data.get("links", [])
        if isinstance(raw_links, list):
            links.extend(str(link).strip() for link in raw_links if isinstance(link, str) and "://" in link)
        direct = data.get("direct", [])
        if isinstance(direct, list):
            for row in direct:
                if isinstance(row, dict) and row.get("enabled", True) and isinstance(row.get("link"), str) and "://" in row["link"]:
                    links.append(row["link"].strip())
    return links


def _all_links(db: Session, sub: Subscription, user: User, token: str) -> list[str]:
    stored = _stored_links(sub)
    return list(dict.fromkeys(stored + _route_links(db, sub, user, token)))


def _html_template(db: Session) -> str:
    return _setting(db, "subscription.html", """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}}</title><style>body{font-family:system-ui;max-width:900px;margin:40px auto;padding:20px;background:#0b1020;color:#fff}a{color:#7dd3fc;word-break:break-all}.card{background:#151b2e;padding:18px;border-radius:14px;margin:14px 0}pre{white-space:pre-wrap}</style></head><body><h1>{{title}}</h1><div class="card"><p>User: {{username}}</p><p>Traffic: {{used_gb}} / {{quota_gb}}</p><p>Expires: {{expires_at}}</p><p>Subscription: <a href="{{subscription_url}}">{{subscription_url}}</a></p></div><div class="card"><h2>Configurations</h2>{{configs_html}}</div></body></html>""")


def _html_response(token: str, request: Request, db: Session, sub: Subscription, user: User, links: list[str]) -> HTMLResponse:
    expires_at = sub.expires_at or user.expires_at
    quota = max(float(user.quota_gb or 0), 0.0)
    used = max(float(user.used_gb or sub.used_gb or 0), 0.0)
    quota_text = "Unlimited" if quota <= 0 else f"{quota:.2f} GB"
    expires_text = expires_at.isoformat() if expires_at else "Unlimited"
    subscription_url = f"{_public_subscription_base(request, db)}{quote(token, safe='')}"
    configs_html = "".join(f'<a href="{html.escape(link, quote=True)}">{html.escape(link)}</a><br>' for link in links) or "<p>No active configurations.</p>"
    values = {"title": html.escape(_setting(db, "subscription.title", "Pars2Ray Subscription")), "username": html.escape(user.username), "used_gb": f"{used:.2f} GB", "quota_gb": quota_text, "expires_at": html.escape(expires_text), "subscription_url": html.escape(subscription_url, quote=True), "configs_html": configs_html}
    rendered = _html_template(db)
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return HTMLResponse(rendered)


def _headers(db: Session, user: User, sub: Subscription) -> dict[str, str]:
    quota = max(float(user.quota_gb or 0), 0.0)
    used = max(float(user.used_gb or sub.used_gb or 0), 0.0)
    expires_at = sub.expires_at or user.expires_at
    expire = int(expires_at.replace(tzinfo=timezone.utc).timestamp()) if expires_at else 0
    total = int(quota * 1024 * 1024 * 1024) if quota > 0 else 0
    used_bytes = int(used * 1024 * 1024 * 1024)
    return {"Subscription-Userinfo": f"upload=0; download={used_bytes}; total={total}; expire={expire}", "Profile-Update-Interval": "12", "Profile-Title": _setting(db, "subscription.title", "Pars2Ray")}


@router.get("/system/subscription-settings")
def get_subscription_settings(db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN"))) -> dict:
    return {"domain": _setting(db, "subscription.domain") or _setting(db, "panel.domain"), "port": int(_setting(db, "subscription.port", "2096") or 2096), "path": _subscription_path(db), "scheme": _setting(db, "subscription.scheme") or ("https" if _setting(db, "panel.tls", "false").lower() == "true" else "http")}


@router.put("/system/subscription-settings")
def update_subscription_settings(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN"))) -> dict:
    domain = str(payload.get("domain") or "").strip().lower().rstrip(".")
    port = int(payload.get("port", 2096))
    path = str(payload.get("path", "/link/")).strip()
    scheme = str(payload.get("scheme", "https")).lower()
    if port < 1 or port > 65535 or scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="invalid_subscription_settings")
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    if domain:
        _set_setting(db, "subscription.domain", domain)
    else:
        _set_setting(db, "subscription.domain", "")
    _set_setting(db, "subscription.port", str(port))
    _set_setting(db, "subscription.path", path)
    _set_setting(db, "subscription.scheme", scheme)
    db.commit()
    return get_subscription_settings(db=db, user=user)


@public_router.get("/link/{token}")
@public_router.get("/sub/{token}")
def subscription(token: str, request: Request, db: Session = Depends(get_db)):
    found = _subscription_rows(db, token)
    if not found:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    sub, user = found
    links = _all_links(db, sub, user, token)
    if "text/html" in (request.headers.get("accept") or "").lower() or request.query_params.get("html") == "1":
        return _html_response(token, request, db, sub, user, links)
    body = "\n".join(links)
    return PlainTextResponse(base64.b64encode(body.encode()).decode(), headers=_headers(db, user, sub), media_type="text/plain; charset=utf-8")


@public_router.get("/link/{token}/raw")
@public_router.get("/sub/{token}/raw")
def subscription_raw(token: str, request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    found = _subscription_rows(db, token)
    if not found:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    sub, user = found
    body = "\n".join(_all_links(db, sub, user, token))
    return PlainTextResponse(body, headers=_headers(db, user, sub), media_type="text/plain; charset=utf-8")
