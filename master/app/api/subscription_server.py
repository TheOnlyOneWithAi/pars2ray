from __future__ import annotations

import base64
import html
import json
from datetime import timezone
from urllib.parse import quote, urlsplit
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import decrypt_secret, encrypt_secret, utcnow
from app.db.base import get_db
from app.models.entities import Node, Plan, Route, Subscription, SystemSetting, User
from app.services.inbound_store import inbounds as inbound_profiles

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


def _subscription_rows(db: Session, username: str) -> tuple[Subscription, User] | None:
    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if not user:
        return None
    subscriptions = db.scalars(select(Subscription).where(Subscription.user_id == user.id, Subscription.enabled.is_(True)).order_by(Subscription.id.desc())).all()
    now = utcnow()
    for sub in subscriptions:
        expires_at = sub.expires_at if sub.expires_at is not None else user.expires_at
        if expires_at is not None and expires_at <= now:
            continue
        plan = db.get(Plan, sub.plan_id) if sub.plan_id is not None else None
        quota_gb = max(float(plan.quota_gb if plan is not None else user.quota_gb or 0), 0.0)
        used_gb = max(float(user.used_gb or 0), float(sub.used_gb or 0), 0.0)
        if quota_gb > 0 and used_gb >= quota_gb:
            continue
        return sub, user
    return None


def _client_id(username: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pars2ray:client:{username.lower()}"))


def _endpoint_host(endpoint: str) -> str:
    value = (endpoint or "").strip()
    parsed = urlsplit(value if "://" in value else f"//{value}")
    return parsed.hostname or ""


def _node_server(db: Session, route: Route) -> str:
    for node_key in route.node_keys:
        node = db.scalar(select(Node).where(Node.node_key == node_key))
        if node and node.endpoint:
            host = _endpoint_host(node.endpoint)
            if host:
                return host
    return ""


def _route_links(db: Session, sub: Subscription, user: User) -> list[str]:
    rows: list[str] = []
    routes = db.scalars(select(Route).where(Route.is_active.is_(True)).order_by(Route.id)).all()
    allowed = set(sub.node_keys or [])
    client_id = _client_id(user.username)
    for route in routes:
        if allowed and not allowed.intersection(route.node_keys):
            continue
        try:
            cfg = json.loads(decrypt_secret(route.config_enc)) if route.config_enc else {}
        except Exception:
            cfg = {}
        server = _node_server(db, route) or str(cfg.get("server_address") or cfg.get("address") or cfg.get("server") or "").strip()
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


def _inbound_links(db: Session, sub: Subscription, user: User) -> list[str]:
    raw = []
    if not sub.config_enc:
        return raw
    try:
        data = json.loads(decrypt_secret(sub.config_enc))
    except Exception:
        return raw
    ids = data.get("inbound_ids", []) if isinstance(data, dict) else []
    if not isinstance(ids, list):
        return raw
    inbound_rows = db.execute(select(inbound_profiles).where(inbound_profiles.c.id.in_([int(i) for i in ids if str(i).isdigit()]))).mappings().all() if ids else []
    node_keys = {str(row["node_key"]) for row in inbound_rows}
    nodes = {n.node_key: n for n in db.scalars(select(Node).where(Node.node_key.in_(node_keys))).all()} if node_keys else {}
    client_id = _client_id(user.username)
    for inbound in inbound_rows:
        node = nodes.get(inbound["node_key"])
        if not node:
            continue
        cfg = inbound["config_json"] or {}
        server = _endpoint_host(node.endpoint)
        if not server:
            continue
        port = int(inbound["port"])
        transport = str(inbound["transport"])
        security = str(inbound["security"])
        params = {"type": "ws" if transport == "websocket" else transport, "security": security}
        if cfg.get("server_name"):
            params["sni"] = str(cfg["server_name"])
        if transport in {"websocket", "httpupgrade", "xhttp"}:
            params["path"] = str(cfg.get("path", "/"))
            if cfg.get("host"):
                params["host"] = str(cfg["host"])
        if transport == "grpc":
            params["serviceName"] = str(cfg.get("service_name", "pars2ray"))
        if security == "reality":
            reality = cfg.get("reality") or {}
            if reality.get("fingerprint"):
                params["fp"] = str(reality["fingerprint"])
            if reality.get("public_key"):
                params["pbk"] = str(reality["public_key"])
            if reality.get("short_id"):
                params["sid"] = str(reality["short_id"])
        query = "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in params.items())
        name = quote(str(inbound["name"]), safe="")
        protocol = str(inbound["protocol"])
        if protocol == "vless":
            raw.append(f"vless://{client_id}@{server}:{port}?{query}#{name}")
        elif protocol == "vmess":
            payload = {"v": "2", "ps": str(inbound["name"]), "add": server, "port": str(port), "id": client_id, "aid": "0", "net": transport, "type": "none", "host": str(cfg.get("host", "")), "path": str(cfg.get("path", "/")), "tls": "tls" if security == "tls" else "", "sni": str(cfg.get("server_name", ""))}
            raw.append("vmess://" + base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode())
        elif protocol == "trojan":
            raw.append(f"trojan://{client_id}@{server}:{port}?{query}#{name}")
        elif protocol == "shadowsocks":
            method = str(cfg.get("method", "aes-128-gcm"))
            auth = base64.urlsafe_b64encode(f"{method}:{client_id}".encode()).decode().rstrip("=")
            raw.append(f"ss://{auth}@{server}:{port}#{name}")
    return raw


def _stored_links(db: Session, sub: Subscription, user: User) -> list[str]:
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
    return list(dict.fromkeys(links + _inbound_links(db, sub, user)))


def _all_links(db: Session, sub: Subscription, user: User) -> list[str]:
    return list(dict.fromkeys(_stored_links(db, sub, user) + _route_links(db, sub, user)))


def _html_template(db: Session) -> str:
    return _setting(db, "subscription.html", """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}}</title><style>body{font-family:system-ui;max-width:900px;margin:40px auto;padding:20px;background:#0b1020;color:#fff}a{color:#7dd3fc;word-break:break-all}.card{background:#151b2e;padding:18px;border-radius:14px;margin:14px 0}pre{white-space:pre-wrap}</style></head><body><h1>{{title}}</h1><div class="card"><p>User: {{username}}</p><p>Traffic: {{used_gb}} / {{quota_gb}}</p><p>Remaining: {{remaining_gb}} ({{remaining_percent}}%)</p><p>Expires: {{expires_at}}</p><p>Days remaining: {{days_remaining}}</p><p>Subscription: <a href="{{subscription_url}}">{{subscription_url}}</a></p><p><a href="{{raw_url}}">Raw configuration subscription</a></p></div><div class="card"><h2>Configurations</h2>{{vless_links}}</div><div class="card"><h2>Connection instructions</h2>{{connection_instructions}}</div><div class="card"><h2>All configurations</h2><pre>{{configs}}</pre></div></body></html>""")


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        for placeholder in ("{{" + key + "}}", "{{" + key.replace("_", r"\_") + "}}"):
            rendered = rendered.replace(placeholder, value)
    return rendered


def _html_response(username: str, request: Request, db: Session, sub: Subscription, user: User, links: list[str]) -> HTMLResponse:
    expires_at = sub.expires_at if sub.expires_at is not None else user.expires_at
    plan = db.get(Plan, sub.plan_id) if sub.plan_id is not None else None
    quota = max(float(plan.quota_gb if plan is not None else user.quota_gb or 0), 0.0)
    used = max(float(user.used_gb or 0), float(sub.used_gb or 0), 0.0)
    unlimited = quota <= 0
    remaining = max(quota - used, 0.0) if not unlimited else 0.0
    remaining_percent = 100.0 if unlimited else max(min((remaining / quota) * 100.0, 100.0), 0.0)
    days_remaining = max((expires_at - utcnow()).days, 0) if expires_at else 0
    subscription_url = f"{_public_subscription_base(request, db)}{quote(username, safe='')}"
    raw_url = subscription_url.rstrip("/") + "/raw"
    configs_html = "".join(f'<a href="{html.escape(link, quote=True)}">{html.escape(link)}</a><br>' for link in links) or "<p>No active configurations.</p>"
    values = {"title": html.escape(_setting(db, "subscription.title", "Pars2Ray Subscription")), "username": html.escape(user.username), "used_gb": f"{used:.2f}", "quota_gb": "Unlimited" if unlimited else f"{quota:.2f}", "remaining_gb": "Unlimited" if unlimited else f"{remaining:.2f}", "remaining_percent": "100" if unlimited else f"{remaining_percent:.1f}", "expires_at": html.escape(expires_at.isoformat() if expires_at else "Unlimited"), "days_remaining": str(days_remaining), "subscription_url": html.escape(subscription_url, quote=True), "raw_url": html.escape(raw_url, quote=True), "vless_links": configs_html, "connection_instructions": "<ol><li>Add the subscription URL to your Xray/V2Ray compatible client.</li><li>Alternatively import an individual configuration above.</li><li>Refresh the subscription when configurations change.</li><li>Keep the subscription URL private.</li></ol>", "configs": html.escape("\n".join(links))}
    return HTMLResponse(_render_template(_html_template(db), values))


def _headers(db: Session, user: User, sub: Subscription) -> dict[str, str]:
    plan = db.get(Plan, sub.plan_id) if sub.plan_id is not None else None
    quota = max(float(plan.quota_gb if plan is not None else user.quota_gb or 0), 0.0)
    used = max(float(user.used_gb or 0), float(sub.used_gb or 0), 0.0)
    expires_at = sub.expires_at if sub.expires_at is not None else user.expires_at
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
    _set_setting(db, "subscription.domain", domain)
    _set_setting(db, "subscription.port", str(port))
    _set_setting(db, "subscription.path", path)
    _set_setting(db, "subscription.scheme", scheme)
    db.commit()
    return get_subscription_settings(db=db, user=user)


@public_router.get("/link/{username}")
@public_router.get("/sub/{username}")
def subscription(username: str, request: Request, db: Session = Depends(get_db)):
    found = _subscription_rows(db, username)
    if not found:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    sub, user = found
    links = _all_links(db, sub, user)
    if "text/html" in (request.headers.get("accept") or "").lower() or request.query_params.get("html") == "1":
        return _html_response(username, request, db, sub, user, links)
    body = "\n".join(links)
    return PlainTextResponse(base64.b64encode(body.encode()).decode(), headers=_headers(db, user, sub), media_type="text/plain; charset=utf-8")


@public_router.get("/link/{username}/raw")
@public_router.get("/sub/{username}/raw")
def subscription_raw(username: str, request: Request, db: Session = Depends(get_db)) -> PlainTextResponse:
    found = _subscription_rows(db, username)
    if not found:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    sub, user = found
    body = "\n".join(_all_links(db, sub, user))
    return PlainTextResponse(body, headers=_headers(db, user, sub), media_type="text/plain; charset=utf-8")
