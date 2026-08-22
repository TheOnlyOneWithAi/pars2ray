from __future__ import annotations

import base64
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_roles
from app.core.security import utcnow
from app.db.base import get_db
from app.models.entities import Node, User
from app.services import agent_client
from app.services.candidate_engine import generate
from app.services.inbound_store import create_client, create_inbound, delete_client, ensure_tables, list_clients, list_inbounds, select_inbound

router = APIRouter(prefix="/api/v1")


class InboundSelection(BaseModel):
    candidate_id: str
    node_key: str
    core: str = Field(pattern="^(xray|sing-box)$")
    protocol: str = Field(pattern="^(vless|vmess|trojan|shadowsocks)$")
    transport: str = Field(pattern="^(tcp|grpc|websocket|httpupgrade|xhttp|quic)$")
    port: int = Field(default=443, ge=1, le=65535)
    security: str = Field(default="reality", pattern="^(none|tls|reality)$")
    name: str = Field(min_length=2, max_length=120)
    config: dict = Field(default_factory=dict)


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    inbound_ids: list[int] = Field(min_length=1, max_length=32)


def _ensure(db: Session) -> None:
    ensure_tables(db.get_bind())


def _score(node: Node, candidate: dict) -> float:
    latency = max(float(node.latency_ms or 0), 1.0)
    cpu = max(float(node.cpu_percent or 0), 0.0)
    memory = max(float(node.memory_percent or 0), 0.0)
    base = float(node.score or 0)
    transport_bonus = {"grpc": 6, "xhttp": 5, "tcp": 3}.get(candidate["transport"], 1)
    security_bonus = 5 if candidate.get("settings", {}).get("security") == "reality" else 2
    return round(base + transport_bonus + security_bonus - latency * 0.08 - cpu * 0.03 - memory * 0.02, 2)


def _vless_link(client: dict, inbound: dict, node: Node) -> str:
    cfg = inbound["config_json"] or {}
    query: dict[str, str] = {"type": inbound["transport"], "security": inbound["security"]}
    if inbound["transport"] in {"websocket", "httpupgrade", "xhttp"}:
        query["path"] = str(cfg.get("path", "/"))
        if cfg.get("host"):
            query["host"] = str(cfg["host"])
    if inbound["transport"] == "grpc":
        query["serviceName"] = str(cfg.get("service_name", "pars2ray"))
    if inbound["security"] in {"tls", "reality"} and cfg.get("server_name"):
        query["sni"] = str(cfg["server_name"])
    if inbound["security"] == "reality":
        query["fp"] = str((cfg.get("reality") or {}).get("fingerprint", "chrome"))
        if (cfg.get("reality") or {}).get("public_key"):
            query["pbk"] = str((cfg.get("reality") or {})["public_key"])
        if (cfg.get("reality") or {}).get("short_id"):
            query["sid"] = str((cfg.get("reality") or {})["short_id"])
    host = node.endpoint.rsplit(":", 1)[0] if ":" in node.endpoint else node.endpoint
    label = quote(client["name"], safe="")
    return f"vless://{client['uuid']}@{host}:{inbound['port']}?{'&'.join(f'{quote(k)}={quote(v)}' for k,v in query.items())}#{label}"


def _config_links(client: dict, selected: list[dict], nodes: dict[str, Node]) -> list[dict]:
    links: list[dict] = []
    for inbound in selected:
        node = nodes.get(inbound["node_key"])
        if not node:
            continue
        if inbound["protocol"] == "vless":
            links.append({"inbound_id": inbound["id"], "protocol": "vless", "link": _vless_link(client, inbound, node)})
        elif inbound["protocol"] == "trojan":
            host = node.endpoint.rsplit(":", 1)[0] if ":" in node.endpoint else node.endpoint
            links.append({"inbound_id": inbound["id"], "protocol": "trojan", "link": f"trojan://{client['uuid']}@{host}:{inbound['port']}#{quote(client['name'])}"})
        elif inbound["protocol"] == "vmess":
            host = node.endpoint.rsplit(":", 1)[0] if ":" in node.endpoint else node.endpoint
            payload = {"v": "2", "ps": client["name"], "add": host, "port": inbound["port"], "id": client["uuid"], "aid": 0, "net": inbound["transport"], "type": "none", "host": (inbound["config_json"] or {}).get("host", ""), "path": (inbound["config_json"] or {}).get("path", "/"), "tls": "tls" if inbound["security"] == "tls" else ""}
            raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
            links.append({"inbound_id": inbound["id"], "protocol": "vmess", "link": f"vmess://{raw}"})
        else:
            links.append({"inbound_id": inbound["id"], "protocol": inbound["protocol"], "link": "", "note": "Use the generated panel config JSON for this protocol."})
    return links


@router.get("/ai/inbounds/recommendations", tags=["ai-inbounds"])
def ai_inbound_recommendations(limit: int = 12, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    _ensure(db)
    nodes = list(db.scalars(select(Node).where(Node.status.in_(["ONLINE", "REGISTERED"]))).all())
    if not nodes:
        return {"candidates": []}
    node_map = {node.node_key: node for node in nodes}
    candidates = generate(list(node_map), max(1, min(limit * 4, 80)))
    ranked = []
    for candidate in candidates:
        node = node_map.get(candidate["path"][0])
        if not node:
            continue
        score = _score(node, candidate)
        ranked.append({**candidate, "score": score, "node": {"node_key": node.node_key, "country": node.country, "endpoint": node.endpoint, "core": node.core, "latency_ms": node.latency_ms}})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {"candidates": ranked[: max(1, min(limit, 50))], "generated_at": utcnow().isoformat()}


@router.post("/ai/inbounds/select", tags=["ai-inbounds"])
async def select_ai_inbound(payload: InboundSelection, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))) -> dict:
    _ensure(db)
    node = db.scalar(select(Node).where(Node.node_key == payload.node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    config = dict(payload.config)
    config.setdefault("port", payload.port)
    config.setdefault("security", payload.security)
    config.setdefault("sniffing", True)
    data = {"name": payload.name, "node_key": node.node_key, "core": payload.core, "protocol": payload.protocol, "port": payload.port, "transport": payload.transport, "security": payload.security, "config_json": config, "score": int(round(_score(node, payload.model_dump()))), "status": "ACTIVE", "is_selected": True, "created_at": utcnow()}
    row = create_inbound(db, data)
    try:
        await agent_client.apply_config(node, {"source": "pars2ray-ai", "inbounds": [row]})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"node_apply_failed: {exc}") from exc
    return row


@router.get("/inbounds", tags=["inbounds"])
def get_inbounds(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    _ensure(db)
    return list_inbounds(db)


@router.post("/users/clients", tags=["client-users"])
def create_client_user(payload: ClientCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))) -> dict:
    _ensure(db)
    selected = []
    for inbound_id in sorted(set(payload.inbound_ids)):
        row = select_inbound(db, inbound_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"inbound_not_found:{inbound_id}")
        selected.append(row)
    client = create_client(db, payload.name, payload.email, payload.inbound_ids)
    nodes = {node.node_key: node for node in db.scalars(select(Node).where(Node.node_key.in_([row["node_key"] for row in selected]))).all()}
    links = _config_links(client, selected, nodes)
    return {"id": client["id"], "name": client["name"], "email": client["email"], "uuid": client["uuid"], "inbound_ids": client["inbound_ids"], "configs": links}


@router.get("/users/clients", tags=["client-users"])
def get_client_users(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    _ensure(db)
    rows = list_clients(db)
    inbounds_by_id = {row["id"]: row for row in list_inbounds(db)}
    node_keys = {row["node_key"] for row in inbounds_by_id.values()}
    nodes = {node.node_key: node for node in db.scalars(select(Node).where(Node.node_key.in_(node_keys))).all()} if node_keys else {}
    out = []
    for client in rows:
        selected = [inbounds_by_id[item] for item in client["inbound_ids"] if item in inbounds_by_id]
        out.append({**client, "configs": _config_links(client, selected, nodes)})
    return out


@router.delete("/users/clients/{client_id}", tags=["client-users"])
def remove_client_user(client_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles("SUPER_ADMIN", "ADMIN"))) -> dict:
    _ensure(db)
    if not delete_client(db, client_id):
        raise HTTPException(status_code=404, detail="client_not_found")
    return {"ok": True}
