from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret
from app.models.entities import Node, SystemSetting, User
from app.services import agent_client
from app.services.candidate_engine import generate
from app.services.config_builder import build_config
from app.services.inbound_store import create_inbound, list_inbounds

LEVELS = {"off": 0, "advisor": 1, "inbounds": 2, "nodes": 3, "autonomous": 4}


@dataclass(frozen=True)
class AIPolicy:
    level: int
    autonomous: bool
    probe_country: str
    max_nodes: int
    max_candidates: int


def _settings(db: Session) -> dict[str, str]:
    rows = db.scalars(select(SystemSetting).where(SystemSetting.key.like("ai.%"))).all()
    out: dict[str, str] = {}
    for row in rows:
        try:
            out[row.key] = decrypt_secret(row.value_enc)
        except Exception:
            out[row.key] = ""
    return out


def policy(db: Session) -> AIPolicy:
    values = _settings(db)
    raw_level = values.get("ai.level", "off").strip().lower()
    try:
        level = max(0, min(4, int(raw_level)))
    except ValueError:
        level = LEVELS.get(raw_level, 0)
    return AIPolicy(
        level=level,
        autonomous=values.get("ai.autonomous", "false").lower() == "true",
        probe_country=values.get("ai.probe_country", "IR").upper(),
        max_nodes=max(1, min(100, int(values.get("ai.max_nodes", "50") or 50))),
        max_candidates=max(1, min(100, int(values.get("ai.max_candidates", "12") or 12))),
    )


def _host(endpoint: str) -> str:
    parsed = urlsplit(endpoint if "://" in endpoint else f"//{endpoint}")
    return parsed.hostname or ""


def _authorized(user: User, required: int) -> bool:
    # Autonomous changes are restricted to the highest administrative role.
    if required >= 4:
        return user.role == "SUPER_ADMIN"
    return user.role in {"SUPER_ADMIN", "ADMIN", "OPERATOR"}


def _candidate_score(node: Node, probe: dict | None) -> float:
    base = float(node.score or 0)
    latency = float((probe or {}).get("latency_ms") or node.latency_ms or 9999)
    loss = float((probe or {}).get("packet_loss_percent") or 100)
    jitter = float((probe or {}).get("jitter_ms") or 9999)
    return round(base + max(0.0, 100.0 - latency) * 0.35 + max(0.0, 100.0 - loss) * 0.45 + max(0.0, 50.0 - jitter) * 0.20, 3)


async def run(db: Session, user: User, dry_run: bool = False) -> dict:
    p = policy(db)
    if not _authorized(user, 4) or p.level < 4 or not p.autonomous:
        raise PermissionError("ai_autonomous_mode_not_authorized")

    nodes = list(db.scalars(select(Node).where(Node.status.in_(["ONLINE", "REGISTERED"])).order_by(Node.score.desc())).all())[: p.max_nodes]
    if not nodes:
        return {"ok": True, "created": [], "tested": [], "probe_node": None, "reason": "no_online_nodes"}

    probe_node = next((n for n in nodes if n.country.upper() == p.probe_country), None)
    if probe_node is None:
        # No Iranian node means there is no valid Iran-origin measurement.
        # We still permit a dry evaluation from the best available node and mark it explicitly.
        probe_node = nodes[0]

    snapshots: list[tuple[Node, dict]] = []
    for node in nodes:
        try:
            snapshots.append((node, await agent_client.config(node)))
        except Exception:
            continue

    candidates = generate([node.node_key for node, _ in snapshots], p.max_candidates, allow_experimental=True)
    ranked: list[dict] = []
    for candidate in candidates:
        node = next((n for n, _ in snapshots if n.node_key == candidate["path"][0]), None)
        if node is None:
            continue
        host = _host(node.endpoint)
        if not host:
            continue
        # Measure the public service from the designated probe node. If an inbound
        # does not exist yet, this is intentionally a post-creation probe.
        ranked.append({"candidate": candidate, "node": node, "host": host})

    created: list[dict] = []
    tested: list[dict] = []
    for item in ranked:
        candidate = item["candidate"]
        node: Node = item["node"]
        transport = candidate["transport"]
        protocol = candidate["protocol"]
        core = candidate["core"]
        # Only generate configurations that the selected core can validate.
        if core == "xray" and protocol == "hysteria2":
            continue
        port = 443
        name = f"AI-{node.node_key}-{protocol}-{transport}"[:120]
        cfg = {"port": port, "security": "reality", "server_name": "www.cloudflare.com", "sniffing": True}
        route = {"name": name, "tag": name, "core": core, "protocol": protocol, "transport": transport, "config": cfg}
        try:
            built = build_config(route, [{"id": "00000000-0000-4000-8000-000000000001", "email": "ai-probe"}])
        except (ValueError, KeyError):
            continue
        if dry_run:
            created.append({"node_key": node.node_key, "name": name, "protocol": protocol, "transport": transport, "core": core, "config": built})
            continue
        try:
            result = await agent_client.apply_config(node, {"core": core, "config": built, "candidate_id": f"ai:{node.node_key}:{protocol}:{transport}", "mode": "autonomous"})
            if not result.get("ok"):
                continue
            row = create_inbound(db, {"name": name, "node_key": node.node_key, "core": core, "protocol": protocol, "port": port, "transport": transport, "security": "reality", "config_json": cfg, "score": 0, "status": "ACTIVE", "is_selected": True})
            created.append(row)
            probe = await agent_client.benchmark(probe_node, {"host": _host(node.endpoint), "port": port, "attempts": 5, "timeout_seconds": 3})
            score = _candidate_score(node, probe)
            tested.append({"inbound_id": row["id"], "node_key": node.node_key, "probe_node": probe_node.node_key, "probe_country": probe_node.country, "probe": probe, "score": score})
        except Exception:
            continue

    # Keep the best generated profiles selected on each node and leave the rest
    # inactive; this prevents autonomous runs from accumulating unbounded junk.
    if not dry_run and created:
        by_node: dict[str, list[tuple[dict, float]]] = {}
        for item in tested:
            by_node.setdefault(item["node_key"], []).append((item, float(item["score"])))
        best_ids = {max(items, key=lambda x: x[1])[0]["inbound_id"] for items in by_node.values() if items}
        for row in list_inbounds(db):
            if row["id"] in {item["id"] for item in created}:
                row_score = next((x["score"] for x in tested if x["inbound_id"] == row["id"]), 0)
                from app.services.inbound_store import set_score
                set_score(db, row["id"], int(round(row_score)), row["id"] in best_ids)

    return {"ok": True, "dry_run": dry_run, "probe_node": {"node_key": probe_node.node_key, "country": probe_node.country, "iran_priority": probe_node.country.upper() == p.probe_country}, "created": created, "tested": tested, "policy": {"level": p.level, "autonomous": p.autonomous}}
