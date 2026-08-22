from __future__ import annotations

from copy import deepcopy
from typing import Any

XRAY_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks"}
SINGBOX_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2"}
TRANSPORTS = {"tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic", "kcp"}


def _transport_settings(transport: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if transport == "tcp": return {"network": "tcp"}
    if transport == "kcp":
        return {"network": "kcp", "kcpSettings": {"mtu": int(cfg.get("mtu", 1350)), "tti": int(cfg.get("tti", 20)), "uplinkCapacity": int(cfg.get("uplink_capacity", 5)), "downlinkCapacity": int(cfg.get("downlink_capacity", 20)), "congestion": bool(cfg.get("congestion", False)), "readBufferSize": int(cfg.get("read_buffer", 2)), "writeBufferSize": int(cfg.get("write_buffer", 2)), "header": {"type": cfg.get("header_type", "none")}}}
    if transport == "websocket": return {"network": "ws", "wsSettings": {"path": cfg.get("path", "/"), "headers": {"Host": cfg["host"]} if cfg.get("host") else {}}}
    if transport == "grpc": return {"network": "grpc", "grpcSettings": {"serviceName": cfg.get("service_name", "pars2ray"), "multiMode": bool(cfg.get("grpc_multi_mode", False))}}
    if transport == "httpupgrade": return {"network": "httpupgrade", "httpupgradeSettings": {"path": cfg.get("path", "/"), "host": cfg.get("host", "")}}
    if transport == "xhttp": return {"network": "xhttp", "xhttpSettings": {"path": cfg.get("path", "/"), "host": cfg.get("host", ""), "mode": cfg.get("xhttp_mode", "auto")}}
    if transport == "quic": return {"network": "quic", "quicSettings": {"security": cfg.get("quic_security", "none"), "key": cfg.get("quic_key", ""), "header": {"type": cfg.get("header_type", "none")}}}
    raise ValueError("unsupported_transport")


def _security_settings(stream: dict[str, Any], cfg: dict[str, Any]) -> None:
    security = str(cfg.get("security") or ("tls" if cfg.get("tls") else "none")).lower()
    if security == "tls":
        stream["security"] = "tls"
        stream["tlsSettings"] = {"serverName": cfg.get("server_name") or cfg.get("host", ""), "alpn": cfg.get("alpn", ["h2", "http/1.1"]), "allowInsecure": bool(cfg.get("allow_insecure", False)), "certificates": cfg.get("certificates", []), "fingerprint": cfg.get("fingerprint", "")}
    elif security == "reality":
        reality = cfg.get("reality") or {}
        stream["security"] = "reality"
        stream["realitySettings"] = {"show": bool(reality.get("show", False)), "dest": reality.get("dest", cfg.get("dest", "www.cloudflare.com:443")), "xver": int(reality.get("xver", 0)), "serverNames": reality.get("server_names", [cfg.get("server_name", "www.cloudflare.com")]), "privateKey": reality.get("private_key", ""), "shortIds": reality.get("short_ids", [reality.get("short_id", "")]), "minClientVer": reality.get("min_client_ver", ""), "maxClientVer": reality.get("max_client_ver", ""), "maxTimeDiff": int(reality.get("max_time_diff", 0)), "fingerprint": reality.get("fingerprint", "chrome")}
    elif security not in {"none", ""}:
        raise ValueError("unsupported_security")


def _common_xray(inbound: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    _security_settings(inbound["streamSettings"], cfg)
    if cfg.get("sniffing"): inbound["sniffing"] = {"enabled": True, "destOverride": cfg.get("sniff_dest_override", ["http", "tls", "quic"]), "metadataOnly": bool(cfg.get("sniff_metadata_only", False))}
    if cfg.get("mux"): inbound["mux"] = {"enabled": True, "concurrency": int(cfg.get("mux_concurrency", 8)), "xudpConcurrency": int(cfg.get("xudp_concurrency", 16)), "xudpProxyUDP443": cfg.get("xudp_proxy_udp443", "reject")}
    if cfg.get("fallbacks"): inbound["settings"]["fallbacks"] = cfg["fallbacks"]
    outbounds = deepcopy(cfg.get("outbounds") or [{"protocol": "freedom", "tag": "direct"}])
    if not any(o.get("tag") == "direct" for o in outbounds): outbounds.append({"protocol": "freedom", "tag": "direct"})
    routing = deepcopy(cfg.get("routing") or {"domainStrategy": "AsIs"})
    if cfg.get("balancers"): routing.setdefault("balancers", cfg["balancers"])
    if cfg.get("routing_rules"): routing.setdefault("rules", cfg["routing_rules"])
    return {"log": {"loglevel": cfg.get("loglevel", "warning")}, "inbounds": [inbound], "outbounds": outbounds, "routing": routing}


def build_xray(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    protocol, transport = str(route["protocol"]).lower(), str(route.get("transport", "tcp")).lower()
    cfg = deepcopy(route.get("config") or {})
    if protocol not in XRAY_PROTOCOLS or transport not in TRANSPORTS: raise ValueError("unsupported_xray_protocol_or_transport")
    inbound = {"tag": route.get("tag", route.get("name", "pars2ray")), "listen": cfg.get("listen", "0.0.0.0"), "port": int(cfg.get("port", 443)), "protocol": protocol, "settings": {}, "streamSettings": _transport_settings(transport, cfg)}
    if protocol in {"vless", "vmess"}:
        inbound["settings"] = {"clients": [{"id": c["id"], **({"email": c["email"]} if c.get("email") else {})} for c in clients]}
        if protocol == "vless": inbound["settings"]["decryption"] = "none"
    elif protocol == "trojan": inbound["settings"] = {"clients": [{"password": c["id"], **({"email": c["email"]} if c.get("email") else {})} for c in clients]}
    else: inbound["settings"] = {"method": cfg.get("method", "2022-blake3-aes-128-gcm"), "password": cfg.get("password") or (clients[0]["id"] if clients else "pars2ray")}
    return _common_xray(inbound, cfg)


def build_singbox(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    protocol, transport = str(route["protocol"]).lower(), str(route.get("transport", "tcp")).lower()
    cfg = deepcopy(route.get("config") or {})
    if protocol not in SINGBOX_PROTOCOLS or transport not in TRANSPORTS: raise ValueError("unsupported_singbox_protocol_or_transport")
    inbound = {"type": protocol, "tag": route.get("tag", route.get("name", "pars2ray")), "listen": cfg.get("listen", "::"), "listen_port": int(cfg.get("port", 443))}
    if protocol in {"vless", "vmess"}: inbound["users"] = [{"uuid": c["id"], **({"name": c["email"]} if c.get("email") else {})} for c in clients]
    elif protocol == "trojan": inbound["users"] = [{"password": c["id"], **({"name": c["email"]} if c.get("email") else {})} for c in clients]
    elif protocol == "shadowsocks": inbound.update({"method": cfg.get("method", "2022-blake3-aes-128-gcm"), "password": cfg.get("password") or (clients[0]["id"] if clients else "pars2ray")})
    else: inbound["users"] = [{"password": c["id"], **({"name": c["email"]} if c.get("email") else {})} for c in clients]
    if transport != "tcp":
        name = {"websocket": "ws", "httpupgrade": "httpupgrade", "xhttp": "http", "grpc": "grpc", "quic": "quic", "kcp": "udp"}[transport]
        inbound["transport"] = {"type": name}
        if transport in {"websocket", "httpupgrade", "xhttp"}: inbound["transport"].update({"path": cfg.get("path", "/"), **({"headers": {"Host": cfg["host"]}} if cfg.get("host") else {})})
        elif transport == "grpc": inbound["transport"]["service_name"] = cfg.get("service_name", "pars2ray")
    security = str(cfg.get("security") or ("tls" if cfg.get("tls") else "none")).lower()
    if security in {"tls", "reality"}: inbound["tls"] = {"enabled": True, "server_name": cfg.get("server_name") or cfg.get("host", ""), "certificate_path": cfg.get("certificate_path", ""), "key_path": cfg.get("key_path", ""), **(cfg.get("tls_settings") or {})}
    if cfg.get("sniffing"): inbound.update({"sniff": True, "sniff_override_destination": True})
    return {"log": {"level": cfg.get("loglevel", "warn")}, "inbounds": [inbound], "outbounds": deepcopy(cfg.get("outbounds") or [{"type": "direct", "tag": "direct"}]), "route": deepcopy(cfg.get("route") or {})}


def build_config(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    return build_singbox(route, clients) if route.get("core") == "sing-box" else build_xray(route, clients)
