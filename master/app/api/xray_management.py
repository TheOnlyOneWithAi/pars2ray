from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import decrypt_secret, encrypt_secret
from app.db.base import get_db
from app.models.entities import Node, Route, User
from app.services.config_builder import build_config

router = APIRouter(prefix="/api/v1/xray", tags=["xray-management"])

CORES = ["xray", "sing-box"]
PROTOCOLS = ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"]
TRANSPORTS = ["tcp", "websocket", "grpc", "httpupgrade", "xhttp", "quic", "kcp"]
SECURITIES = ["none", "tls", "reality"]
ROUTE_ROLES = ("SUPER_ADMIN", "ADMIN", "OPERATOR")


def _config(route: Route) -> dict[str, Any]:
    if not route.config_enc:
        return {}
    try:
        value = json.loads(decrypt_secret(route.config_enc))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _get_route(route_id: int, db: Session) -> Route:
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="route_not_found")
    return route


def _validate_route_fields(
    core: str,
    protocol: str,
    transport: str,
) -> None:
    if core not in CORES:
        raise HTTPException(status_code=422, detail="unsupported_core")
    if protocol not in PROTOCOLS:
        raise HTTPException(status_code=422, detail="unsupported_protocol")
    if transport not in TRANSPORTS:
        raise HTTPException(status_code=422, detail="unsupported_transport")
    if core == "xray" and protocol == "hysteria2":
        raise HTTPException(status_code=422, detail="hysteria2_requires_sing_box")


@router.get("/capabilities")
def capabilities(
    user: User = Depends(
        require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR", "RESELLER")
    ),
) -> dict[str, Any]:
    return {
        "cores": CORES,
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
def get_xray_route(
    route_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ROUTE_ROLES)),
) -> dict[str, Any]:
    route = _get_route(route_id, db)
    return {
        "id": route.id,
        "name": route.name,
        "node_keys": route.node_keys,
        "core": route.core,
        "protocol": route.protocol,
        "transport": route.transport,
        "config": _config(route),
    }


@router.put("/routes/{route_id}")
def update_xray_route(
    route_id: int,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ROUTE_ROLES)),
) -> dict[str, Any]:
    route = _get_route(route_id, db)
    core = payload.get("core", route.core)
    protocol = payload.get("protocol", route.protocol)
    transport = payload.get("transport", route.transport)
    _validate_route_fields(core, protocol, transport)

    config = payload.get("config", {})
    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config_must_be_object")

    node_keys = [str(value) for value in payload.get("node_keys", route.node_keys)]
    if not node_keys or len(node_keys) > 20:
        raise HTTPException(status_code=422, detail="invalid_node_keys")

    existing = {
        node.node_key
        for node in db.scalars(select(Node).where(Node.node_key.in_(node_keys))).all()
    }
    if set(node_keys) != existing:
        raise HTTPException(status_code=422, detail="unknown_node")

    route.core = core
    route.protocol = protocol
    route.transport = transport
    route.node_keys = node_keys
    route.config_enc = encrypt_secret(json.dumps(config, separators=(",", ":")))
    db.commit()
    return get_xray_route(route_id, db, user)


@router.post("/routes/{route_id}/validate")
def validate_xray_route(
    route_id: int,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ROUTE_ROLES)),
) -> dict[str, Any]:
    route = _get_route(route_id, db)
    cfg = (payload or {}).get("config", _config(route))
    if not isinstance(cfg, dict):
        return {"ok": False, "errors": ["config_must_be_object"]}

    errors: list[str] = []
    try:
        built = build_config(
            {
                "name": route.name,
                "core": route.core,
                "protocol": route.protocol,
                "transport": route.transport,
                "config": cfg,
            },
            [{"id": "00000000-0000-4000-8000-000000000001", "email": "validation"}],
        )
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "errors": [str(exc)]}

    inbound = (built.get("inbounds") or [{}])[0]
    try:
        port = int(inbound.get("port", inbound.get("listen_port", 443)))
        if port not in range(1, 65536):
            errors.append("invalid_port")
    except (TypeError, ValueError):
        errors.append("invalid_port")

    if route.core == "xray" and cfg.get("security") == "reality":
        reality = cfg.get("reality", {})
        if not isinstance(reality, dict):
            errors.append("reality_must_be_object")
        elif not reality.get("private_key") or not reality.get("short_id"):
            errors.append("reality_requires_private_key_and_short_id")

    return {"ok": not errors, "errors": errors, "config": built}


@router.get("/nodes")
def xray_nodes(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ROUTE_ROLES)),
) -> list[dict[str, Any]]:
    nodes = db.scalars(select(Node).order_by(Node.country, Node.node_key)).all()
    return [
        {
            "node_key": node.node_key,
            "country": node.country,
            "core": node.core,
            "core_version": node.core_version,
            "status": node.status,
            "capabilities": node.capabilities,
        }
        for node in nodes
    ]
