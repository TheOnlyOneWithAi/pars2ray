from __future__ import annotations

import hashlib
import json

SUPPORTED_PROTOCOLS = ["vless", "trojan", "shadowsocks"]
SUPPORTED_TRANSPORTS = ["tcp", "grpc", "websocket", "httpupgrade", "xhttp"]
SUPPORTED_CORES = ["xray", "sing-box"]


def make_id(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def generate(nodes: list[str], max_candidates: int = 30, allow_experimental: bool = False) -> list[dict]:
    if max_candidates <= 0 or not nodes:
        return []

    clean_nodes = list(dict.fromkeys(str(node).strip() for node in nodes if str(node).strip()))
    if not clean_nodes:
        return []

    transports = SUPPORTED_TRANSPORTS if allow_experimental else ["tcp", "grpc", "xhttp"]
    out: list[dict] = []
    seen: set[str] = set()

    for node in clean_nodes:
        for core in SUPPORTED_CORES:
            for protocol in SUPPORTED_PROTOCOLS:
                for transport in transports:
                    candidate = {"path": [node], "core": core, "protocol": protocol, "transport": transport, "settings": {}}
                    candidate_id = make_id(candidate)
                    if candidate_id in seen:
                        continue
                    seen.add(candidate_id)
                    candidate["candidate_id"] = candidate_id
                    out.append(candidate)
                    if len(out) >= max_candidates:
                        return out
    return out
