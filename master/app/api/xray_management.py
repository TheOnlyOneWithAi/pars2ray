from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import encrypt_secret, decrypt_secret
from app.db.base import get_db
from app.models.entities import Node, Route, User
from app.services.config_builder import build_config

router = APIRouter(prefix="/api/v1/xray", tags=["xray-management"])

PROTOCOLS = ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"]
TRANSPORTS = ["tcp", "websocket", "grpc", "httpupgrade", "xhttp", "quic"]
SECURITIES = ["none", "tls", "reality"]


def _config(route: Route) -> dict[str, Any]:
    if not route.config_enc:
        return {}
    try:
        return json.loads(decrypt_secret(route.config_enc))
    except Exception:
        return {}


@router.get("/capabilities")
def capabilities(user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR", "RESELLER"))) -> dict[str, Any]:
    return {
        "cores": ["xray", "sing-box"],
        "protocols": PROTOCOLS,
        "transports": TRANSPORTS,
        "security": SECURITIES,
        "features": {
            "reality": True,
            "tls": True,
            "fallbacks": True,
            "sniffing": True,
            "mux": True,
            "routing": True,
            "outbounds": True,
            "balancers": True,
            "subscription": True,
            "per_client_quota": True,
        },
    }


@router.get("/routes/{route_id}")
def get_xray_route(route_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))) -> dict[str, Any]:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="route_not_found")
    cfg = _config(route)
    return {
        "id": route.id,
        "name": route.name,
        "node_keys": route.node_keys,
        "core": route.core,
        "protocol": route.protocol,
        "transport": route.transport,
        "config": cfg,
    }


@router.put("/routes/{route_id}")
def update_xray_route(route_id: int, payload: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))) -> dict[str, Any]:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="route_not_found")
    if payload.get("protocol") not in PROTOCOLS:
        raise HTTPException(status_code=422, detail="unsupported_protocol")
    if payload.get("transport") not in TRANSPORTS:
        raise HTTPException(status_code=422, detail="unsupported_transport")
    config = payload.get("config", {})
    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config_must_be_object")
    route.protocol = str(payload["protocol"])
    route.transport = str(payload["transport"])
    route.core = str(payload.get("core", route.core))
    route.node_keys = [str(x) for x in payload.get("node_keys", route.node_keys)]
    route.config_enc = encrypt_secret(json.dumps(config, separators=(",", ":")))
    db.commit()
    return get_xray_route(route_id, db, user)


@router.post("/routes/{route_id}/validate")
def validate_xray_route(route_id: int, payload: dict[str, Any] | None = None, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))) -> dict[str, Any]:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="route_not_found")
    cfg = (payload or {}).get("config", _config(route))
    try:
        built = build_config({"name": route.name, "core": route.core, "protocol": route.protocol, "transport": route.transport, "config": cfg}, [{"id": "00000000-0000-4000-8000-000000000001", "email": "validation"}])
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "errors": [str(exc)]}
    errors: list[str] = []
    inbound = (built.get("inbounds") or [{}])[0]
    if int(inbound.get("port", inbound.get("listen_port", 443))) not in range(1, 65536):
        errors.append("invalid_port")
    if route.core == "xray" and cfg.get("security") == "reality":
        reality = cfg.get("reality", {})
        if not reality.get("private_key") or not reality.get("short_id"):
            errors.append("reality_requires_private_key_and_short_id")
    return {"ok": not errors, "errors": errors, "config": built}


@router.get("/nodes")
def xray_nodes(db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))) -> list[dict[str, Any]]:
    nodes = db.scalars(select(Node).order_by(Node.country, Node.node_key)).all()
    return [{"node_key": n.node_key, "country": n.country, "core": n.core, "core_version": n.core_version, "status": n.status, "capabilities": n.capabilities} for n in nodes]
