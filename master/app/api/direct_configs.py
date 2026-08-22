from __future__ import annotations

import base64
import json
import secrets
from urllib.parse import quote, urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_roles
from app.core.security import decrypt_secret, encrypt_secret, utcnow
from app.db.base import get_db
from app.models.entities import Node, Subscription, User
from app.services.audit import record
from app.services.config_decision import decide_config
from app.api.subscription_server import _public_subscription_base, _setting, _subscription_path

router = APIRouter(prefix="/api/v1", tags=["direct-configs"])


class DirectConfigCreate(BaseModel):
    subscription_id: int = Field(ge=1)
    protocol: str = Field(pattern="^(vless|vmess|shadowsocks)$")
    name: str = Field(default="Pars2Ray", min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    port: int = Field(default=443, ge=1, le=65535)
    node_key: str | None = Field(default=None, max_length=40)
    uuid: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=512)
    method: str | None = Field(default=None, max_length=64)
    transport: str = Field(default="tcp", pattern="^(tcp|grpc|websocket|httpupgrade|xhttp|quic)$")
    security: str = Field(default="none", pattern="^(none|tls|reality)$")
    sni: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    path: str = Field(default="/", max_length=2048)
    service_name: str | None = Field(default=None, max_length=255)
    flow: str | None = Field(default=None, max_length=64)
    fingerprint: str | None = Field(default=None, max_length=64)
    public_key: str | None = Field(default=None, max_length=256)
    short_id: str | None = Field(default=None, max_length=128)
    alter_id: int = Field(default=0, ge=0, le=65535)
    replace: bool = False


class DirectConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None


def _load(sub: Subscription) -> list[dict]:
    if not sub.config_enc:
        return []
    try:
        data = json.loads(decrypt_secret(sub.config_enc))
        return data.get("direct", []) if isinstance(data, dict) else []
    except Exception:
        return []


def _save(sub: Subscription, rows: list[dict]) -> None:
    existing: dict = {}
    if sub.config_enc:
        try:
            existing = json.loads(decrypt_secret(sub.config_enc))
        except Exception:
            existing = {}
    existing["direct"] = rows
    sub.config_enc = encrypt_secret(json.dumps(existing, separators=(",", ":")))


def _owner(user: User, sub: Subscription) -> None:
    if user.role not in {"SUPER_ADMIN", "ADMIN"} and sub.user_id != user.id:
        raise HTTPException(status_code=403, detail="forbidden")


def _entitlement(user: User, sub: Subscription) -> None:
    if not sub.enabled:
        raise HTTPException(status_code=409, detail="subscription_inactive")
    expires_at = sub.expires_at if sub.expires_at is not None else user.expires_at
    if expires_at is not None and expires_at <= utcnow():
        raise HTTPException(status_code=409, detail="subscription_expired")
    quota = max(float(user.quota_gb or 0), 0.0)
    used = max(float(user.used_gb or 0), float(sub.used_gb or 0), 0.0)
    if quota > 0 and used >= quota:
        raise HTTPException(status_code=409, detail="traffic_quota_exceeded")


def _endpoint_host(endpoint: str) -> str:
    value = endpoint.strip()
    if not value:
        return ""
    parsed = urlsplit(value if "://" in value else f"//{value}")
    return parsed.hostname or ""


def _address(payload: DirectConfigCreate, db: Session, request: Request) -> tuple[str, dict]:
    if payload.address:
        address = _endpoint_host(payload.address) or payload.address.strip()
        return address, {"source": "explicit"}
    if payload.node_key:
        node = db.scalar(select(Node).where(Node.node_key == payload.node_key.upper()))
        if not node:
            raise HTTPException(status_code=404, detail="node_not_found")
        host = _endpoint_host(node.endpoint or "")
        if host:
            return host, {"source": "node", "node_key": payload.node_key.upper()}
    for key in ("server.public_ip", "subscription.domain", "panel.domain"):
        value = _setting(db, key)
        if value:
            host = _endpoint_host(value)
            if host:
                return host, {"source": key}
    host = _endpoint_host(request.headers.get("host") or request.url.hostname or "")
    if host:
        return host, {"source": "request_host"}
    raise HTTPException(status_code=422, detail="server_address_unavailable")


def _build(payload: DirectConfigCreate, db: Session, request: Request, decision: dict | None = None) -> tuple[str, dict]:
    address, address_meta = _address(payload, db, request)
    selected = {"protocol": payload.protocol, "port": payload.port, "transport": payload.transport, "security": payload.security, "sni": payload.sni, "host": payload.host, "path": payload.path, "service_name": payload.service_name, "flow": payload.flow, "fingerprint": payload.fingerprint, "public_key": payload.public_key, "short_id": payload.short_id}
    if decision:
        selected.update({k: v for k, v in decision.items() if v is not None})
    uid = payload.uuid or str(uuid4())
    name = quote(payload.name, safe="")
    query: dict[str, str] = {"type": selected["transport"], "security": selected["security"]}
    if selected["security"] in {"tls", "reality"} and selected.get("sni"):
        query["sni"] = str(selected["sni"])
    if selected["security"] == "reality":
        if selected.get("fingerprint"):
            query["fp"] = str(selected["fingerprint"])
        if selected.get("public_key"):
            query["pbk"] = str(selected["public_key"])
        if selected.get("short_id"):
            query["sid"] = str(selected["short_id"])
    if selected.get("flow"):
        query["flow"] = str(selected["flow"])
    if selected["transport"] in {"websocket", "httpupgrade", "xhttp"}:
        query["path"] = str(selected.get("path") or "/")
        if selected.get("host"):
            query["host"] = str(selected["host"])
    if selected["transport"] == "grpc" and selected.get("service_name"):
        query["serviceName"] = str(selected["service_name"])
    query_text = "&".join(f"{quote(k)}={quote(str(v))}" for k, v in query.items())
    protocol = selected["protocol"]
    port = int(selected["port"])
    if protocol == "vless":
        link = f"vless://{uid}@{address}:{port}?{query_text}#{name}"
    elif protocol == "vmess":
        obj = {"v": "2", "ps": payload.name, "add": address, "port": str(port), "id": uid, "aid": payload.alter_id, "scy": "auto", "net": selected["transport"], "type": "none", "host": selected.get("host") or "", "path": selected.get("path") or "/", "tls": "tls" if selected["security"] == "tls" else "", "sni": selected.get("sni") or ""}
        link = "vmess://" + base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()
    else:
        method = payload.method or "aes-128-gcm"
        secret = payload.password or secrets.token_urlsafe(18)
        userinfo = base64.urlsafe_b64encode(f"{method}:{secret}".encode()).decode().rstrip("=")
        link = f"ss://{userinfo}@{address}:{port}#{name}"
    row = {"id": str(uuid4()), "name": payload.name, "protocol": protocol, "link": link, "address": address, "port": port, "node_key": payload.node_key.upper() if payload.node_key else None, "enabled": True, "created_at": utcnow().isoformat(), "decision": selected, "address_source": address_meta["source"]}
    return link, row


@router.get("/subscriptions/{subscription_id}/direct-configs")
def list_direct_configs(subscription_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    _owner(user, sub)
    return {"subscription_id": sub.id, "configs": _load(sub)}


@router.post("/subscriptions/{subscription_id}/direct-configs", status_code=201)
async def create_direct_config(subscription_id: int, payload: DirectConfigCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER", "USER"))) -> dict:
    if payload.subscription_id != subscription_id:
        raise HTTPException(status_code=422, detail="subscription_id_mismatch")
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    _owner(user, sub)
    target = db.get(User, sub.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user_not_found")
    _entitlement(target, sub)
    address, address_meta = _address(payload, db, request)
    fallback = {"protocol": payload.protocol, "port": payload.port, "transport": payload.transport, "security": payload.security, "sni": payload.sni, "host": payload.host, "path": payload.path, "service_name": payload.service_name, "flow": payload.flow, "fingerprint": payload.fingerprint, "public_key": payload.public_key, "short_id": payload.short_id}
    snapshot = {"server": address, "address_source": address_meta["source"], "node_key": payload.node_key, "requested": fallback, "supported": {"protocols": ["vless", "vmess", "shadowsocks"], "transports": ["tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"], "security": ["none", "tls", "reality"]}, "goal": "secure, compatible, low overhead"}
    selected, ai_meta = await decide_config(snapshot, fallback)
    payload_data = payload.model_dump()
    for key in fallback:
        if key in selected:
            payload_data[key] = selected[key]
    effective = DirectConfigCreate(**payload_data)
    link, row = _build(effective, db, request, selected)
    rows = [] if payload.replace else _load(sub)
    rows.append(row)
    if len(rows) > 100:
        raise HTTPException(status_code=422, detail="too_many_direct_configs")
    _save(sub, rows)
    record(db, user, "subscription.direct_config.create", "subscription", str(sub.id), request.client.host if request.client else "", {"protocol": effective.protocol, "name": effective.name, "ai_enabled": bool(ai_meta.get("enabled")), "address_source": row["address_source"]})
    db.commit()
    base = _public_subscription_base(request, db)
    origin = base.split(_subscription_path(db), 1)[0]
    raw_token = decrypt_secret(sub.token_enc) if sub.token_enc else ""
    subscription_url = f"{origin}/s/{quote(raw_token, safe='')}" if raw_token else f"{base}{quote(target.username, safe='')}"
    return {"ok": True, "config": row, "link": link, "subscription_url": subscription_url, "raw_url": f"{subscription_url}/raw", "inbound_required": False, "credential_source": "protocol_generated", "ai": ai_meta}


@router.patch("/subscriptions/{subscription_id}/direct-configs/{config_id}")
def update_direct_config(subscription_id: int, config_id: str, payload: DirectConfigUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER", "USER"))) -> dict:
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    _owner(user, sub)
    rows = _load(sub)
    row = next((item for item in rows if item.get("id") == config_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="direct_config_not_found")
    if payload.name is not None:
        row["name"] = payload.name
    if payload.enabled is not None:
        row["enabled"] = payload.enabled
    _save(sub, rows)
    record(db, user, "subscription.direct_config.update", "subscription", str(sub.id), request.client.host if request.client else "", {"config_id": config_id})
    db.commit()
    return {"ok": True, "config": row}


@router.delete("/subscriptions/{subscription_id}/direct-configs/{config_id}")
def delete_direct_config(subscription_id: int, config_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER", "USER"))) -> dict:
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    _owner(user, sub)
    rows = _load(sub)
    kept = [item for item in rows if item.get("id") != config_id]
    if len(kept) == len(rows):
        raise HTTPException(status_code=404, detail="direct_config_not_found")
    _save(sub, kept)
    record(db, user, "subscription.direct_config.delete", "subscription", str(sub.id), request.client.host if request.client else "", {"config_id": config_id})
    db.commit()
    return {"ok": True}
