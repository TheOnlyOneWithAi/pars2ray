from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles, request_ip
from app.core.security import decrypt_secret, encrypt_secret
from app.db.base import get_db
from app.models.entities import Node, SystemSetting, User
from app.services import agent_client
from app.services.audit import record

router = APIRouter(prefix="/api/v1/control", tags=["control-plane"])
ADMIN_ROLES = ("SUPER_ADMIN", "ADMIN", "OPERATOR")
ROOT_ROLES = ("SUPER_ADMIN", "ADMIN")

KEYS = {
    "outbounds": "xray.outbounds", "routing": "xray.routing", "balancers": "xray.balancers",
    "fallbacks": "xray.fallbacks", "templates": "xray.templates", "geo": "xray.geo",
    "fail2ban": "security.fail2ban", "telegram": "integration.telegram", "panel": "panel.settings",
}
DEFAULTS: dict[str, Any] = {
    "outbounds": [], "routing": {"domainStrategy": "AsIs", "rules": []}, "balancers": [], "fallbacks": [],
    "templates": {}, "geo": {"geoip_url": "", "geosite_url": "", "updated_at": None},
    "fail2ban": {"enabled": False, "jail": "pars2ray", "maxretry": 3, "findtime": 600, "bantime": 3600},
    "telegram": {"enabled": False, "bot_token": "", "chat_ids": []},
    "panel": {"path": "", "tls": False, "trusted_proxies": []},
}
OUTBOUND_PROTOCOLS = {"freedom", "blackhole", "dns", "http", "socks", "vmess", "vless", "trojan", "shadowsocks", "wireguard", "loopback"}


def _load(db: Session, name: str) -> Any:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == KEYS[name]))
    if not row: return deepcopy(DEFAULTS[name])
    try: return json.loads(decrypt_secret(row.value_enc))
    except (ValueError, TypeError, json.JSONDecodeError) as exc: raise HTTPException(status_code=500, detail=f"invalid_control_setting:{name}") from exc


def _save(db: Session, name: str, value: Any) -> None:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == KEYS[name]))
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if not row: db.add(SystemSetting(key=KEYS[name], value_enc=encrypt_secret(encoded), is_secret=name in {"telegram", "panel"}))
    else: row.value_enc = encrypt_secret(encoded)


def _validate(name: str, value: Any) -> Any:
    if name == "outbounds":
        if not isinstance(value, list) or len(value) > 200: raise HTTPException(status_code=422, detail="outbounds_must_be_list")
        tags: set[str] = set()
        for item in value:
            if not isinstance(item, dict) or not item.get("protocol") or not item.get("tag"): raise HTTPException(status_code=422, detail="invalid_outbound")
            if item["tag"] in tags: raise HTTPException(status_code=422, detail="duplicate_outbound_tag")
            if item["protocol"] not in OUTBOUND_PROTOCOLS: raise HTTPException(status_code=422, detail=f"unsupported_outbound_protocol:{item['protocol']}")
            tags.add(item["tag"])
    elif name == "routing":
        if not isinstance(value, dict) or not isinstance(value.get("rules", []), list): raise HTTPException(status_code=422, detail="invalid_routing")
        if len(value.get("rules", [])) > 500: raise HTTPException(status_code=422, detail="too_many_routing_rules")
    elif name in {"balancers", "fallbacks"}:
        if not isinstance(value, list) or len(value) > 200: raise HTTPException(status_code=422, detail=f"{name}_must_be_list")
    elif name == "templates":
        if not isinstance(value, dict) or len(value) > 100: raise HTTPException(status_code=422, detail="invalid_templates")
        if any(not isinstance(k, str) or not isinstance(v, str) or len(v) > 200_000 for k, v in value.items()): raise HTTPException(status_code=422, detail="invalid_template")
    elif name == "geo":
        if not isinstance(value, dict): raise HTTPException(status_code=422, detail="invalid_geo_settings")
    elif name == "fail2ban":
        if not isinstance(value, dict): raise HTTPException(status_code=422, detail="invalid_fail2ban_settings")
        value = {**DEFAULTS["fail2ban"], **value}
        for field in ("maxretry", "findtime", "bantime"):
            value[field] = int(value[field])
            if value[field] <= 0: raise HTTPException(status_code=422, detail=f"invalid_fail2ban_{field}")
    elif name == "telegram":
        if not isinstance(value, dict): raise HTTPException(status_code=422, detail="invalid_telegram_settings")
        value = {**DEFAULTS["telegram"], **value}
        if not isinstance(value["chat_ids"], list): raise HTTPException(status_code=422, detail="telegram_chat_ids_must_be_list")
    elif name == "panel":
        if not isinstance(value, dict): raise HTTPException(status_code=422, detail="invalid_panel_settings")
    return value


def _commit_audit(db: Session, user: User, request: Request, action: str, target: str) -> None:
    record(db, user, action, "control", target, request_ip(request)); db.commit()


@router.get("/capabilities")
def control_capabilities(user: User = Depends(require_roles(*ADMIN_ROLES))) -> dict[str, Any]:
    return {"cores": ["xray", "sing-box"], "protocols": ["vless", "vmess", "trojan", "shadowsocks", "wireguard", "hysteria2", "http", "socks", "dokodemo-door", "tunnel", "tun", "mixed", "mtproto"], "transports": ["tcp", "kcp", "websocket", "grpc", "httpupgrade", "xhttp", "quic"], "security": ["none", "tls", "reality", "xtls"], "outbound_protocols": sorted(OUTBOUND_PROTOCOLS), "features": ["fallbacks", "routing", "balancers", "outbounds", "geoip", "geosite", "fail2ban", "telegram", "templates", "backup", "multi-node", "per-client-limits"]}


@router.get("/settings")
def get_control_settings(db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))) -> dict[str, Any]:
    return {name: _load(db, name) for name in KEYS}


@router.put("/settings/{name}")
def put_control_setting(name: str, payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    if name not in KEYS: raise HTTPException(status_code=404, detail="control_setting_not_found")
    value = _validate(name, payload.get("value")); _save(db, name, value); _commit_audit(db, user, request, f"control.{name}.update", name)
    return {"ok": True, "name": name, "value": value}


@router.get("/{name}")
def get_control_setting(name: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))) -> dict[str, Any]:
    if name not in KEYS: raise HTTPException(status_code=404, detail="control_setting_not_found")
    return {"name": name, "value": _load(db, name)}


@router.get("/outbounds/list")
def list_outbounds(db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))) -> dict[str, Any]: return {"items": _load(db, "outbounds")}


@router.post("/outbounds")
def create_outbound(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    items = _load(db, "outbounds"); item = deepcopy(payload); item.pop("id", None)
    if not item.get("tag") or item.get("protocol") not in OUTBOUND_PROTOCOLS: raise HTTPException(status_code=422, detail="invalid_outbound")
    if any(x.get("tag") == item["tag"] for x in items): raise HTTPException(status_code=409, detail="duplicate_outbound_tag")
    item["id"] = f"ob-{len(items)+1:04d}"; items.append(item); _save(db, "outbounds", _validate("outbounds", items)); _commit_audit(db, user, request, "outbound.create", item["id"])
    return {"ok": True, "item": item}


@router.put("/outbounds/{outbound_id}")
def update_outbound(outbound_id: str, payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    items = _load(db, "outbounds"); target = next((x for x in items if x.get("id") == outbound_id or x.get("tag") == outbound_id), None)
    if target is None: raise HTTPException(status_code=404, detail="outbound_not_found")
    target.update({k: v for k, v in payload.items() if k != "id"}); _save(db, "outbounds", _validate("outbounds", items)); _commit_audit(db, user, request, "outbound.update", outbound_id)
    return {"ok": True, "item": target}


@router.delete("/outbounds/{outbound_id}")
def delete_outbound(outbound_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    items = _load(db, "outbounds"); remaining = [x for x in items if x.get("id") != outbound_id and x.get("tag") != outbound_id]
    if len(remaining) == len(items): raise HTTPException(status_code=404, detail="outbound_not_found")
    _save(db, "outbounds", remaining); _commit_audit(db, user, request, "outbound.delete", outbound_id); return {"ok": True, "deleted": outbound_id}


@router.get("/routing/rules")
def list_routing_rules(db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))) -> dict[str, Any]: return {"rules": _load(db, "routing").get("rules", [])}


@router.put("/routing")
def replace_routing(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    value = _validate("routing", payload); _save(db, "routing", value); _commit_audit(db, user, request, "routing.replace", "routing"); return {"ok": True, "routing": value}


@router.post("/routing/rules")
def create_routing_rule(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    value = _load(db, "routing"); rules = value.setdefault("rules", []); rule = deepcopy(payload); rule["id"] = rule.get("id") or f"route-{len(rules)+1:04d}"; rules.append(rule); value = _validate("routing", value); _save(db, "routing", value); _commit_audit(db, user, request, "routing.rule.create", rule["id"]); return {"ok": True, "rule": rule}


@router.delete("/routing/rules/{rule_id}")
def delete_routing_rule(rule_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    value = _load(db, "routing"); rules = value.get("rules", []); remaining = [r for r in rules if r.get("id") != rule_id]
    if len(remaining) == len(rules): raise HTTPException(status_code=404, detail="routing_rule_not_found")
    value["rules"] = remaining; _save(db, "routing", _validate("routing", value)); _commit_audit(db, user, request, "routing.rule.delete", rule_id); return {"ok": True, "deleted": rule_id}


@router.get("/balancers")
def list_balancers(db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))) -> dict[str, Any]: return {"items": _load(db, "balancers")}


@router.put("/balancers")
def replace_balancers(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    value = _validate("balancers", payload.get("items", [])); _save(db, "balancers", value); _commit_audit(db, user, request, "balancers.replace", "balancers"); return {"ok": True, "items": value}


@router.get("/fallbacks")
def list_fallbacks(db: Session = Depends(get_db), user: User = Depends(require_roles(*ADMIN_ROLES))) -> dict[str, Any]: return {"items": _load(db, "fallbacks")}


@router.put("/fallbacks")
def replace_fallbacks(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    value = _validate("fallbacks", payload.get("items", [])); _save(db, "fallbacks", value); _commit_audit(db, user, request, "fallbacks.replace", "fallbacks"); return {"ok": True, "items": value}


@router.post("/nodes/{node_key}/compose")
async def compose_node(node_key: str, payload: dict[str, Any] | None = None, request: Request = None, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node: raise HTTPException(status_code=404, detail="node_not_found")
    try: current = await agent_client.config(node)
    except Exception as exc: raise HTTPException(status_code=502, detail="node_unreachable") from exc
    config = deepcopy(current.get("config") or {}); core = current.get("core") or node.core or "xray"
    if not isinstance(config, dict): raise HTTPException(status_code=502, detail="node_config_invalid")
    if core == "xray":
        config["outbounds"] = _load(db, "outbounds") or config.get("outbounds", [])
        config["routing"] = _load(db, "routing") or config.get("routing", {})
        fallbacks = _load(db, "fallbacks")
        if fallbacks:
            for inbound in config.get("inbounds", []):
                if isinstance(inbound, dict): inbound.setdefault("settings", {})["fallbacks"] = fallbacks
    elif core == "sing-box":
        config["outbounds"] = _load(db, "outbounds") or config.get("outbounds", [])
        config["route"] = _load(db, "routing") or config.get("route", {})
    if payload and isinstance(payload.get("patch"), dict): config.update(payload["patch"])
    result = await agent_client.apply_config(node, {"core": core, "config": config, "operation_id": f"compose:{node_key}", "mode": "control-plane"})
    if not result.get("ok"): raise HTTPException(status_code=502, detail={"code": "node_apply_failed", "result": result})
    _commit_audit(db, user, request, "control.compose", node_key)
    return {"ok": True, "node_key": node_key, "core": core, "config": config, "result": result}


@router.post("/nodes/{node_key}/rollback")
async def rollback_node(node_key: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node: raise HTTPException(status_code=404, detail="node_not_found")
    try: result = await agent_client.rollback(node, f"control-rollback:{node_key}")
    except Exception as exc: raise HTTPException(status_code=502, detail="node_unreachable") from exc
    _commit_audit(db, user, request, "control.rollback", node_key); return result
