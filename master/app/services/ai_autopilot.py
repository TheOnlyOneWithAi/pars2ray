from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models.entities import Node, SystemSetting, User
from app.services import agent_client
from app.services.candidate_engine import generate
from app.services.config_builder import build_config
from app.services.inbound_store import create_inbound, list_inbounds, set_score

LEVELS = {"off": 0, "advisor": 1, "inbounds": 2, "nodes": 3, "autonomous": 4}


@dataclass(frozen=True)
class AIPolicy:
    enabled: bool
    level: int
    autonomous: bool
    failover_on_iran_disconnect: bool
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

    def bounded(name: str, default: int) -> int:
        try:
            return max(1, min(100, int(values.get(name, str(default)) or default)))
        except ValueError:
            return default

    return AIPolicy(
        enabled=values.get("ai.enabled", "false").lower() == "true",
        level=level,
        autonomous=values.get("ai.autonomous", "false").lower() == "true",
        failover_on_iran_disconnect=values.get(
            "ai.failover_on_iran_disconnect", "true"
        ).lower()
        == "true",
        probe_country=values.get("ai.probe_country", "IR").upper(),
        max_nodes=bounded("ai.max_nodes", 50),
        max_candidates=bounded("ai.max_candidates", 12),
    )


def _host(endpoint: str) -> str:
    parsed = urlsplit(endpoint if "://" in endpoint else f"//{endpoint}")
    return parsed.hostname or ""


def _candidate_score(node: Node, probe: dict | None) -> float:
    data = probe or {}
    base = float(node.score or 0)
    latency = float(data.get("latency_ms") or node.latency_ms or 9999)
    loss = float(data.get("packet_loss_percent") or 100)
    jitter = float(data.get("jitter_ms") or 9999)
    return round(
        base
        + max(0.0, 100.0 - latency) * 0.35
        + max(0.0, 100.0 - loss) * 0.45
        + max(0.0, 50.0 - jitter) * 0.20,
        3,
    )


def _safe_port(existing: set[int], seed: int) -> int:
    port = 20000 + (seed % 20000)
    for _ in range(20000):
        if port not in existing:
            return port
        port = 20000 + ((port - 19999) % 20000)
    raise RuntimeError("no_free_autonomous_port")


async def run(
    db: Session,
    user: User | None,
    dry_run: bool = False,
    internal_trigger: str | None = None,
) -> dict:
    p = policy(db)
    trusted_internal = internal_trigger == "iran_node_disconnect"
    if not p.enabled or p.level < 4 or not p.autonomous:
        raise PermissionError("ai_autonomous_mode_not_authorized")
    if not trusted_internal and (user is None or user.role != "SUPER_ADMIN"):
        raise PermissionError("ai_autonomous_mode_not_authorized")

    nodes = list(
        db.scalars(
            select(Node)
            .where(Node.status.in_(["ONLINE", "REGISTERED"]))
            .order_by(Node.score.desc())
        ).all()
    nodes = nodes[: p.max_nodes]
    if not nodes:
        return {
            "ok": True,
            "created": [],
            "tested": [],
            "probe_node": None,
            "reason": "no_online_nodes",
            "trigger": internal_trigger,
        }

    probe_node = next(
        (node for node in nodes if node.country.upper() == p.probe_country),
        nodes[0],
    )
    snapshots: list[tuple[Node, dict]] = []
    for node in nodes:
        try:
            snapshots.append((node, await agent_client.config(node)))
        except Exception:
            continue
    if not snapshots:
        return {
            "ok": True,
            "created": [],
            "tested": [],
            "probe_node": probe_node.node_key,
            "reason": "nodes_unreachable",
            "trigger": internal_trigger,
        }

    existing_ports: dict[str, set[int]] = {}
    for row in list_inbounds(db):
        try:
            existing_ports.setdefault(str(row["node_key"]), set()).add(int(row["port"]))
        except (TypeError, ValueError):
            continue

    candidates = generate(
        [node.node_key for node, _ in snapshots],
        max(p.max_candidates * 3, p.max_candidates),
        allow_experimental=True,
    )
    protocol_rank = {"vless": 4, "trojan": 3, "shadowsocks": 2}
    transport_rank = {"grpc": 4, "xhttp": 3, "tcp": 2, "websocket": 1}
    selected: dict[str, dict] = {}
    for candidate in candidates:
        if candidate["core"] == "xray" and candidate["protocol"] == "hysteria2":
            continue
        key = candidate["path"][0]
        rank = (
            protocol_rank.get(candidate["protocol"], 0),
            transport_rank.get(candidate["transport"], 0),
            candidate["core"] == "xray",
        )
        if key not in selected or rank > selected[key]["_rank"]:
            selected[key] = {**candidate, "_rank": rank}
    selected = dict(list(selected.items())[: p.max_candidates])

    created: list[dict] = []
    tested: list[dict] = []
    for node, _ in snapshots:
        candidate = selected.get(node.node_key)
        if not candidate:
            continue
        host = _host(node.endpoint)
        if not host:
            continue
        protocol = candidate["protocol"]
        transport = candidate["transport"]
        core = candidate["core"]
        port = _safe_port(
            existing_ports.setdefault(node.node_key, set()),
            sum(ord(char) for char in f"{node.node_key}:{protocol}:{transport}"),
        )
        name = f"AI-{node.node_key}-{protocol}-{transport}"[:120]
        cfg = {"port": port, "security": "none", "sniffing": True}
        route = {
            "name": name,
            "tag": name,
            "core": core,
            "protocol": protocol,
            "transport": transport,
            "config": cfg,
        }
        try:
            built = build_config(
                route,
                [{"id": "00000000-0000-4000-8000-000000000001", "email": "ai-probe"}],
            )
        except (ValueError, KeyError):
            continue
        if dry_run:
            created.append(
                {
                    "node_key": node.node_key,
                    "name": name,
                    "protocol": protocol,
                    "transport": transport,
                    "core": core,
                    "port": port,
                    "config": built,
                }
            )
            continue
        try:
            result = await agent_client.apply_config(
                node,
                {
                    "core": core,
                    "config": built,
                    "candidate_id": f"ai:{node.node_key}:{protocol}:{transport}:{port}",
                    "mode": "autonomous",
                },
            )
            if not result.get("ok"):
                continue
            row = create_inbound(
                db,
                {
                    "name": name,
                    "node_key": node.node_key,
                    "core": core,
                    "protocol": protocol,
                    "port": port,
                    "transport": transport,
                    "security": "none",
                    "config_json": cfg,
                    "score": 0,
                    "status": "ACTIVE",
                    "is_selected": True,
                },
            )
            created.append(row)
            probe = await agent_client.benchmark(
                probe_node,
                {
                    "host": host,
                    "port": port,
                    "attempts": 5,
                    "timeout_seconds": 3,
                },
            )
            score = _candidate_score(node, probe)
            set_score(db, int(row["id"]), int(round(score)), True)
            tested.append(
                {
                    "inbound_id": row["id"],
                    "node_key": node.node_key,
                    "probe_node": probe_node.node_key,
                    "probe_country": probe_node.country,
                    "iran_priority": probe_node.country.upper() == p.probe_country,
                    "probe": probe,
                    "score": score,
                }
            )
        except Exception:
            continue
    return {
        "ok": True,
        "dry_run": dry_run,
        "probe_node": {
            "node_key": probe_node.node_key,
            "country": probe_node.country,
            "iran_priority": probe_node.country.upper() == p.probe_country,
        },
        "created": created,
        "tested": tested,
        "trigger": internal_trigger,
        "policy": {
            "enabled": p.enabled,
            "level": p.level,
            "autonomous": p.autonomous,
            "failover_on_iran_disconnect": p.failover_on_iran_disconnect,
        },
    }
