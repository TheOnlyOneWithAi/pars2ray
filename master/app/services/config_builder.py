from __future__ import annotations

from copy import deepcopy
from typing import Any


PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2"}
TRANSPORTS = {"tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"}


def _transport_settings(transport: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if transport == "tcp":
        return {"network": "tcp"}
    if transport == "websocket":
        return {"network": "ws", "wsSettings": {"path": cfg.get("path", "/"), "headers": {"Host": cfg.get("host", "")}}}
    if transport == "grpc":
        return {"network": "grpc", "grpcSettings": {"serviceName": cfg.get("service_name", "pars2ray")}}
    if transport == "httpupgrade":
        return {"network": "httpupgrade", "httpupgradeSettings": {"path": cfg.get("path", "/"), "host": cfg.get("host", "")}}
    if transport == "xhttp":
        return {"network": "xhttp", "xhttpSettings": {"path": cfg.get("path", "/"), "host": cfg.get("host", "")}}
    if transport == "quic":
        return {"network": "quic", "quicSettings": {"security": cfg.get("quic_security", "none"), "key": cfg.get("quic_key", "")}}
    raise ValueError("unsupported_transport")


def build_xray(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    protocol = str(route["protocol"]).lower()
    transport = str(route.get("transport", "tcp")).lower()
    cfg = deepcopy(route.get("config") or {})
    if protocol not in PROTOCOLS or transport not in TRANSPORTS:
        raise ValueError("unsupported_protocol_or_transport")
    inbound: dict[str, Any] = {
        "tag": route.get("tag", route.get("name", "pars2ray")),
        "listen": cfg.get("listen", "0.0.0.0"),
        "port": int(cfg.get("port", 443)),
        "protocol": protocol,
        "settings": {},
        "streamSettings": _transport_settings(transport, cfg),
    }
    if protocol in {"vless", "vmess"}:
        inbound["settings"] = {"clients": [{"id": c["id"], **({"email": c["email"]} if c.get("email") else {})} for c in clients], "decryption": "none" if protocol == "vless" else None}
        if protocol == "vless":
            inbound["settings"].pop("decryption", None)
            inbound["settings"]["decryption"] = "none"
    elif protocol == "trojan":
        inbound["settings"] = {"clients": [{"password": c["id"], **({"email": c["email"]} if c.get("email") else {})} for c in clients]}
    elif protocol == "shadowsocks":
        inbound["settings"] = {"method": cfg.get("method", "2022-blake3-aes-128-gcm"), "password": cfg.get("password") or (clients[0]["id"] if clients else "pars2ray")}
    elif protocol == "hysteria2":
        inbound["settings"] = {"users": [{"password": c["id"], **({"name": c["email"]} if c.get("email") else {})} for c in clients]}
    tls = bool(cfg.get("tls", False))
    if tls:
        security = inbound.setdefault("streamSettings", {}).setdefault("security", "tls")
        if security == "tls":
            inbound["streamSettings"]["tlsSettings"] = {"serverName": cfg.get("server_name") or cfg.get("host", ""), "certificates": cfg.get("certificates", [])}
    return {"log": {"loglevel": cfg.get("loglevel", "warning")}, "inbounds": [inbound], "outbounds": [{"protocol": "freedom", "tag": "direct"}], "routing": {"domainStrategy": "AsIs"}}


def build_singbox(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    protocol = str(route["protocol"]).lower()
    transport = str(route.get("transport", "tcp")).lower()
    cfg = deepcopy(route.get("config") or {})
    if protocol not in PROTOCOLS or transport not in TRANSPORTS:
        raise ValueError("unsupported_protocol_or_transport")
    inbound: dict[str, Any] = {"type": protocol, "tag": route.get("tag", route.get("name", "pars2ray")), "listen": cfg.get("listen", "::"), "listen_port": int(cfg.get("port", 443))}
    if protocol in {"vless", "vmess"}:
        inbound["users"] = [{"uuid": c["id"], **({"name": c["email"]} if c.get("email") else {})} for c in clients]
    elif protocol == "trojan":
        inbound["users"] = [{"password": c["id"], **({"name": c["email"]} if c.get("email") else {})} for c in clients]
    elif protocol == "shadowsocks":
        inbound["method"] = cfg.get("method", "2022-blake3-aes-128-gcm")
        inbound["password"] = cfg.get("password") or (clients[0]["id"] if clients else "pars2ray")
    elif protocol == "hysteria2":
        inbound["users"] = [{"password": c["id"], **({"name": c["email"]} if c.get("email") else {})} for c in clients]
    if transport != "tcp":
        inbound["transport"] = {"type": transport}
        if transport in {"websocket", "httpupgrade", "xhttp"}:
            inbound["transport"]["path"] = cfg.get("path", "/")
            if cfg.get("host"):
                inbound["transport"]["headers"] = {"Host": cfg["host"]}
        elif transport == "grpc":
            inbound["transport"]["service_name"] = cfg.get("service_name", "pars2ray")
    if cfg.get("tls"):
        inbound["tls"] = {"enabled": True, "server_name": cfg.get("server_name") or cfg.get("host", ""), "certificate_path": cfg.get("certificate_path", ""), "key_path": cfg.get("key_path", "")}
    return {"log": {"level": cfg.get("loglevel", "warn")}, "inbounds": [inbound], "outbounds": [{"type": "direct", "tag": "direct"}]}


def build_config(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    if route.get("core") == "sing-box":
        return build_singbox(route, clients)
    return build_xray(route, clients)
