from __future__ import annotations

import hashlib
import json

SUPPORTED_PROTOCOLS = [
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "wireguard",
    "hysteria2",
    "tunnel",
    "mixed",
    "http",
    "socks",
    "dokodemo-door",
    "tun",
    "mtproto",
]
SUPPORTED_SINGBOX_PROTOCOLS = [
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "hysteria2",
    "mixed",
    "tun",
]
SUPPORTED_TRANSPORTS = [
    "tcp",
    "grpc",
    "websocket",
    "httpupgrade",
    "xhttp",
    "quic",
    "kcp",
]
SUPPORTED_CORES = ["xray", "sing-box"]


def make_id(obj: dict) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def _protocol_matrix() -> list[tuple[str, str]]:
    """Return a deterministic, fair core/protocol order.

    A simple core-major loop can exhaust the candidate budget with Xray
    entries before sing-box capabilities are ever represented. Round-robin
    by protocol position keeps the bounded AI search space representative.
    """
    matrix: list[tuple[str, str]] = []
    max_len = max(len(SUPPORTED_PROTOCOLS), len(SUPPORTED_SINGBOX_PROTOCOLS))
    for index in range(max_len):
        if index < len(SUPPORTED_PROTOCOLS):
            matrix.append(("xray", SUPPORTED_PROTOCOLS[index]))
        if index < len(SUPPORTED_SINGBOX_PROTOCOLS):
            matrix.append(("sing-box", SUPPORTED_SINGBOX_PROTOCOLS[index]))
    return matrix


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
        for core, protocol in _protocol_matrix():
            for transport in transports:
                candidate = {
                    "path": [node],
                    "core": core,
                    "protocol": protocol,
                    "transport": transport,
                    "settings": {},
                }
                candidate_id = make_id(candidate)
                if candidate_id in seen:
                    continue
                seen.add(candidate_id)
                candidate["candidate_id"] = candidate_id
                out.append(candidate)
                if len(out) >= max_candidates:
                    return out
    return out
