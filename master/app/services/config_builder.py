from __future__ import annotations

from copy import deepcopy
from typing import Any

XRAY_PROTOCOLS = {
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "wireguard",
    "tunnel",
    "mixed",
    "http",
    "socks",
    "dokodemo-door",
    "tun",
    "mtproto",
}
SINGBOX_PROTOCOLS = {
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "hysteria2",
    "mixed",
    "tun",
}
TRANSPORTS = {"tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic", "kcp"}


def _transport_settings(transport: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if transport == "tcp":
        return {"network": "tcp"}
    if transport == "kcp":
        return {
            "network": "kcp",
            "kcpSettings": {
                "mtu": int(cfg.get("mtu", 1350)),
                "tti": int(cfg.get("tti", 20)),
                "uplinkCapacity": int(cfg.get("uplink_capacity", 5)),
                "downlinkCapacity": int(cfg.get("downlink_capacity", 20)),
                "congestion": bool(cfg.get("congestion", False)),
                "readBufferSize": int(cfg.get("read_buffer", 2)),
                "writeBufferSize": int(cfg.get("write_buffer", 2)),
                "header": {"type": cfg.get("header_type", "none")},
            },
        }
    if transport == "websocket":
        return {
            "network": "ws",
            "wsSettings": {
                "path": cfg.get("path", "/"),
                "headers": {"Host": cfg["host"]} if cfg.get("host") else {},
            },
        }
    if transport == "grpc":
        return {
            "network": "grpc",
            "grpcSettings": {
                "serviceName": cfg.get("service_name", "pars2ray"),
                "multiMode": bool(cfg.get("grpc_multi_mode", False)),
            },
        }
    if transport == "httpupgrade":
        return {
            "network": "httpupgrade",
            "httpupgradeSettings": {
                "path": cfg.get("path", "/"),
                "host": cfg.get("host", ""),
            },
        }
    if transport == "xhttp":
        return {
            "network": "xhttp",
            "xhttpSettings": {
                "path": cfg.get("path", "/"),
                "host": cfg.get("host", ""),
                "mode": cfg.get("xhttp_mode", "auto"),
            },
        }
    if transport == "quic":
        return {
            "network": "quic",
            "quicSettings": {
                "security": cfg.get("quic_security", "none"),
                "key": cfg.get("quic_key", ""),
                "header": {"type": cfg.get("header_type", "none")},
            },
        }
    raise ValueError("unsupported_transport")


def _security_settings(stream: dict[str, Any], cfg: dict[str, Any]) -> None:
    security = str(cfg.get("security") or ("tls" if cfg.get("tls") else "none")).lower()
    if security == "tls":
        stream["security"] = "tls"
        stream["tlsSettings"] = {
            "serverName": cfg.get("server_name") or cfg.get("host", ""),
            "alpn": cfg.get("alpn", ["h2", "http/1.1"]),
            "allowInsecure": bool(cfg.get("allow_insecure", False)),
            "certificates": cfg.get("certificates", []),
            "fingerprint": cfg.get("fingerprint", ""),
        }
    elif security == "reality":
        reality = cfg.get("reality") or {}
        stream["security"] = "reality"
        stream["realitySettings"] = {
            "show": bool(reality.get("show", False)),
            "dest": reality.get("dest", cfg.get("dest", "www.cloudflare.com:443")),
            "xver": int(reality.get("xver", 0)),
            "serverNames": reality.get(
                "server_names", [cfg.get("server_name", "www.cloudflare.com")]
            ),
            "privateKey": reality.get("private_key", ""),
            "shortIds": reality.get("short_ids", [reality.get("short_id", "")]),
            "minClientVer": reality.get("min_client_ver", ""),
            "maxClientVer": reality.get("max_client_ver", ""),
            "maxTimeDiff": int(reality.get("max_time_diff", 0)),
            "fingerprint": reality.get("fingerprint", "chrome"),
        }
    elif security not in {"none", ""}:
        raise ValueError("unsupported_security")


def _common_xray(inbound: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    if inbound.get("streamSettings") is not None:
        _security_settings(inbound["streamSettings"], cfg)
    if cfg.get("sniffing"):
        inbound["sniffing"] = {
            "enabled": True,
            "destOverride": cfg.get("sniff_dest_override", ["http", "tls", "quic"]),
            "metadataOnly": bool(cfg.get("sniff_metadata_only", False)),
        }
    if cfg.get("mux"):
        inbound["mux"] = {
            "enabled": True,
            "concurrency": int(cfg.get("mux_concurrency", 8)),
            "xudpConcurrency": int(cfg.get("xudp_concurrency", 16)),
            "xudpProxyUDP443": cfg.get("xudp_proxy_udp443", "reject"),
        }
    if cfg.get("fallbacks"):
        inbound.setdefault("settings", {})["fallbacks"] = cfg["fallbacks"]
    outbounds = deepcopy(cfg.get("outbounds") or [{"protocol": "freedom", "tag": "direct"}])
    if not any(outbound.get("tag") == "direct" for outbound in outbounds):
        outbounds.append({"protocol": "freedom", "tag": "direct"})
    return {
        "log": {"loglevel": cfg.get("loglevel", "warning")},
        "inbounds": [inbound],
        "outbounds": outbounds,
        "routing": deepcopy(cfg.get("routing") or {"domainStrategy": "AsIs"}),
    }


def build_xray(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    protocol = str(route["protocol"]).lower()
    transport = str(route.get("transport", "tcp")).lower()
    cfg = deepcopy(route.get("config") or {})
    if protocol not in XRAY_PROTOCOLS or transport not in TRANSPORTS:
        raise ValueError("unsupported_xray_protocol_or_transport")
    tcp_only = {
        "wireguard",
        "tunnel",
        "mixed",
        "http",
        "socks",
        "dokodemo-door",
        "tun",
        "mtproto",
    }
    if protocol in tcp_only and transport != "tcp":
        raise ValueError("advanced_protocol_requires_tcp")
    inbound: dict[str, Any] = {
        "tag": route.get("tag", route.get("name", "pars2ray")),
        "port": int(cfg.get("port", 443)),
        "protocol": protocol,
        "settings": {},
    }
    if cfg.get("listen"):
        inbound["listen"] = cfg["listen"]
    if protocol in {"vless", "vmess"}:
        inbound["streamSettings"] = _transport_settings(transport, cfg)
        inbound["settings"] = {
            "clients": [
                {"id": client["id"], **({"email": client["email"]} if client.get("email") else {})}
                for client in clients
            ]
        }
        if protocol == "vless":
            inbound["settings"]["decryption"] = "none"
    elif protocol == "trojan":
        inbound["streamSettings"] = _transport_settings(transport, cfg)
        inbound["settings"] = {
            "clients": [
                {"password": client["id"], **({"email": client["email"]} if client.get("email") else {})}
                for client in clients
            ]
        }
    elif protocol == "shadowsocks":
        inbound["streamSettings"] = _transport_settings(transport, cfg)
        inbound["settings"] = {
            "method": cfg.get("method", "2022-blake3-aes-128-gcm"),
            "password": cfg.get("password") or (clients[0]["id"] if clients else "pars2ray"),
            "email": cfg.get("email", ""),
            "network": cfg.get("network", "tcp,udp"),
        }
    elif protocol == "http":
        inbound["settings"] = {
            "accounts": [
                {"user": client.get("email") or client["id"], "pass": cfg.get("password") or client["id"]}
                for client in clients
            ],
            "allowTransparent": bool(cfg.get("allow_transparent", False)),
        }
    elif protocol == "socks":
        inbound["settings"] = {
            "auth": cfg.get("auth", "password" if clients else "noauth"),
            "accounts": [
                {"user": client.get("email") or client["id"], "pass": cfg.get("password") or client["id"]}
                for client in clients
            ],
            "udp": bool(cfg.get("udp", True)),
        }
    elif protocol == "dokodemo-door":
        inbound["settings"] = {
            "address": cfg.get("address", "127.0.0.1"),
            "port": int(cfg.get("target_port", 80)),
            "network": cfg.get("network", "tcp,udp"),
            "followRedirect": bool(cfg.get("follow_redirect", False)),
        }
    elif protocol in {"wireguard", "tun", "tunnel", "mixed", "mtproto"}:
        inbound["settings"] = deepcopy(cfg.get("settings") or {})
    return _common_xray(inbound, cfg)


def build_singbox(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    protocol = str(route["protocol"]).lower()
    transport = str(route.get("transport", "tcp")).lower()
    cfg = deepcopy(route.get("config") or {})
    if protocol not in SINGBOX_PROTOCOLS or transport not in TRANSPORTS:
        raise ValueError("unsupported_singbox_protocol_or_transport")
    inbound: dict[str, Any] = {
        "type": protocol,
        "tag": route.get("tag", route.get("name", "pars2ray")),
        "listen": cfg.get("listen", "::"),
        "listen_port": int(cfg.get("port", 443)),
    }
    if protocol in {"vless", "vmess"}:
        inbound["users"] = [
            {"uuid": client["id"], **({"name": client["email"]} if client.get("email") else {})}
            for client in clients
        ]
    elif protocol == "trojan":
        inbound["users"] = [
            {"password": client["id"], **({"name": client["email"]} if client.get("email") else {})}
            for client in clients
        ]
    elif protocol == "shadowsocks":
        inbound.update(
            {
                "method": cfg.get("method", "2022-blake3-aes-128-gcm"),
                "password": cfg.get("password") or (clients[0]["id"] if clients else "pars2ray"),
            }
        )
    elif protocol == "hysteria2":
        inbound["users"] = [
            {"password": client["id"], **({"name": client["email"]} if client.get("email") else {})}
            for client in clients
        ]
        inbound["up_mbps"] = int(cfg.get("up_mbps", 100))
        inbound["down_mbps"] = int(cfg.get("down_mbps", 100))
    elif protocol == "mixed":
        inbound["users"] = [
            {"username": client.get("email") or client["id"], "password": client["id"]}
            for client in clients
        ]
    elif protocol == "tun":
        inbound.update(deepcopy(cfg.get("settings") or {}))
    if transport != "tcp" and protocol not in {"hysteria2", "tun"}:
        name = {
            "websocket": "ws",
            "httpupgrade": "httpupgrade",
            "xhttp": "http",
            "grpc": "grpc",
            "quic": "quic",
            "kcp": "udp",
        }[transport]
        inbound["transport"] = {"type": name}
        if transport in {"websocket", "httpupgrade", "xhttp"}:
            inbound["transport"].update(
                {
                    "path": cfg.get("path", "/"),
                    **({"headers": {"Host": cfg["host"]}} if cfg.get("host") else {}),
                }
            )
        elif transport == "grpc":
            inbound["transport"]["service_name"] = cfg.get("service_name", "pars2ray")
    security = str(cfg.get("security") or ("tls" if cfg.get("tls") else "none")).lower()
    if security in {"tls", "reality"}:
        inbound["tls"] = {
            "enabled": True,
            "server_name": cfg.get("server_name") or cfg.get("host", ""),
            "certificate_path": cfg.get("certificate_path", ""),
            "key_path": cfg.get("key_path", ""),
            **(cfg.get("tls_settings") or {}),
        }
    if cfg.get("sniffing"):
        inbound.update({"sniff": True, "sniff_override_destination": True})
    return {
        "log": {"level": cfg.get("loglevel", "warn")},
        "inbounds": [inbound],
        "outbounds": deepcopy(cfg.get("outbounds") or [{"type": "direct", "tag": "direct"}]),
        "route": deepcopy(cfg.get("route") or {}),
    }


def build_config(route: dict[str, Any], clients: list[dict[str, Any]]) -> dict[str, Any]:
    if route.get("core") == "sing-box":
        return build_singbox(route, clients)
    return build_xray(route, clients)
