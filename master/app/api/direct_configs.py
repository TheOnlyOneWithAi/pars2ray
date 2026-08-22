from __future__ import annotations

import base64
import json
from urllib.parse import quote
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
from app.api.subscription_server import _public_subscription_base

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


def _address(payload: DirectConfigCreate, db: Session) -> str:
    if payload.address:
        return payload.address.strip()
    if payload.node_key:
        node = db.scalar(select(Node).where(Node.node_key == payload.node_key.upper()))
        if not node:
            raise HTTPException(status_code=404, detail="node_not_found")
        return node.endpoint.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0]
    raise HTTPException(status_code=422, detail="address_or_node_required")


def _build(payload: DirectConfigCreate, db: Session) -> tuple[str, dict]:
    address = _address(payload, db)
    uid = payload.uuid or str(uuid4())
    name = quote(payload.name, safe="")
    query: dict[str, str] = {"type": payload.transport, "security": payload.security}
    if payload.security in {"tls", "reality"} and payload.sni:
        query["sni"] = payload.sni
    if payload.security == "reality":
        if payload.fingerprint:
            query["fp"] = payload.fingerprint
        if payload.public_key:
            query["pbk"] = payload.public_key
        if payload.short_id:
            query["sid"] = payload.short_id
    if payload.flow:
        query["flow"] = payload.flow
    if payload.transport in {"websocket", "httpupgrade", "xhttp"}:
        query["path"] = payload.path
        if payload.host:
            query["host"] = payload.host
    if payload.transport == "grpc" and payload.service_name:
        query["serviceName"] = payload.service_name
    query_text = "&".join(f"{quote(k)}={quote(str(v))}" for k, v in query.items())
    if payload.protocol == "vless":
        link = f"vless://{uid}@{address}:{payload.port}?{query_text}#{name}"
    elif payload.protocol == "vmess":
        obj = {"v": "2", "ps": payload.name, "add": address, "port": str(payload.port), "id": uid, "aid": payload.alter_id, "scy": "auto", "net": payload.transport, "type": "none", "host": payload.host or "", "path": payload.path, "tls": "tls" if payload.security == "tls" else "", "sni": payload.sni or ""}
        link = "vmess://" + base64.b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode()
    else:
        method = payload.method or "aes-128-gcm"
        secret = payload.password or __import__("secrets").token_urlsafe(18)
        userinfo = base64.urlsafe_b64encode(f"{method}:{secret}".encode()).decode().rstrip("=")
        link = f"ss://{userinfo}@{address}:{payload.port}#{name}"
    return link, {"id": str(uuid4()), "name": payload.name, "protocol": payload.protocol, "link": link, "address": address, "port": payload.port, "node_key": payload.node_key.upper() if payload.node_key else None, "enabled": True, "created_at": utcnow().isoformat()}


@router.get("/subscriptions/{subscription_id}/direct-configs")
def list_direct_configs(subscription_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    _owner(user, sub)
    return {"subscription_id": sub.id, "configs": _load(sub)}


@router.post("/subscriptions/{subscription_id}/direct-configs", status_code=201)
def create_direct_config(subscription_id: int, payload: DirectConfigCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "RESELLER", "USER"))) -> dict:
    if payload.subscription_id != subscription_id:
        raise HTTPException(status_code=422, detail="subscription_id_mismatch")
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription_not_found")
    _owner(user, sub)
    if not sub.enabled:
        raise HTTPException(status_code=409, detail="subscription_inactive")
    expires_at = sub.expires_at
    if expires_at is not None and expires_at <= utcnow():
        raise HTTPException(status_code=409, detail="subscription_expired")
    link, row = _build(payload, db)
    rows = [] if payload.replace else _load(sub)
    rows.append(row)
    if len(rows) > 100:
        raise HTTPException(status_code=422, detail="too_many_direct_configs")
    _save(sub, rows)
    record(db, user, "subscription.direct_config.create", "subscription", str(sub.id), request.client.host if request.client else "", {"protocol": payload.protocol, "name": payload.name})
    db.commit()
    base = _public_subscription_base(request, db)
    subscription_url = f"{base}{quote(user.username, safe='')}"
    return {"ok": True, "config": row, "link": link, "subscription_url": subscription_url, "raw_url": f"{subscription_url}/raw", "inbound_required": False, "credential_source": "protocol_generated"}


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
