from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from app.services.core_manager import ACTIVE, PREVIOUS, _atomic_copy, _state_lock, capability

ALLOWED_XRAY = {"vless", "vmess", "trojan", "shadowsocks", "http", "socks", "dokodemo-door", "wireguard", "tun"}
ALLOWED_SINGBOX = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2"}
ALLOWED_TRANSPORTS = {"tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic", "kcp"}


def current_config() -> dict:
    if not ACTIVE.exists():
        return {"core": capability().get("active_core", "none"), "config": None, "inbounds": []}
    with ACTIVE.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    return {"core": capability().get("active_core", "none"), "config": config, "inbounds": _public_inbounds(config)}


def _public_inbounds(config: dict) -> list[dict]:
    rows = []
    for item in config.get("inbounds", []) if isinstance(config, dict) else []:
        if not isinstance(item, dict):
            continue
        rows.append({"tag": str(item.get("tag", "")), "protocol": item.get("protocol", item.get("type", "")), "transport": _transport(item), "listen": item.get("listen", ""), "port": item.get("port", item.get("listen_port"))})
    return rows


def _transport(item: dict) -> str:
    if isinstance(item.get("streamSettings"), dict):
        return str(item["streamSettings"].get("network", "tcp"))
    transport = item.get("transport")
    if isinstance(transport, dict):
        return str(transport.get("type", "tcp"))
    return "tcp"


def _apply_xray(item: dict, protocol: str, transport: str) -> None:
    item["protocol"] = protocol
    stream = item.setdefault("streamSettings", {})
    if not isinstance(stream, dict): raise ValueError("invalid_xray_stream_settings")
    stream["network"] = transport
    if transport == "tcp":
        for key in ("wsSettings", "grpcSettings", "httpupgradeSettings", "xhttpSettings", "kcpSettings", "quicSettings"): stream.pop(key, None)
    elif transport == "websocket":
        stream.setdefault("wsSettings", {}); [stream.pop(key, None) for key in ("grpcSettings", "httpupgradeSettings", "xhttpSettings", "kcpSettings", "quicSettings")]
    elif transport == "grpc":
        stream.setdefault("grpcSettings", {}); [stream.pop(key, None) for key in ("wsSettings", "httpupgradeSettings", "xhttpSettings", "kcpSettings", "quicSettings")]
    elif transport == "httpupgrade":
        stream.setdefault("httpupgradeSettings", {}); [stream.pop(key, None) for key in ("wsSettings", "grpcSettings", "xhttpSettings", "kcpSettings", "quicSettings")]
    elif transport == "xhttp":
        stream.setdefault("xhttpSettings", {}); [stream.pop(key, None) for key in ("wsSettings", "grpcSettings", "httpupgradeSettings", "kcpSettings", "quicSettings")]
    elif transport == "quic":
        stream.setdefault("quicSettings", {}); [stream.pop(key, None) for key in ("wsSettings", "grpcSettings", "httpupgradeSettings", "xhttpSettings", "kcpSettings")]
    elif transport == "kcp":
        stream.setdefault("kcpSettings", {}); [stream.pop(key, None) for key in ("wsSettings", "grpcSettings", "httpupgradeSettings", "xhttpSettings", "quicSettings")]
    else:
        raise ValueError("unsupported_transport")


def _apply_singbox(item: dict, protocol: str, transport: str) -> None:
    item["type"] = protocol
    if transport == "tcp": item.pop("transport", None)
    else:
        item["transport"] = {"type": transport, **(item.get("transport") or {})}
        item["transport"]["type"] = transport


def update_existing_inbounds(updates: list[dict]) -> dict:
    if not isinstance(updates, list) or not updates: return {"ok": False, "reason": "no_inbound_updates"}
    with _state_lock():
        if not ACTIVE.exists(): return {"ok": False, "reason": "no_active_config"}
        with ACTIVE.open("r", encoding="utf-8") as handle: config = json.load(handle)
        inbounds = config.get("inbounds")
        if not isinstance(inbounds, list): return {"ok": False, "reason": "inbounds_missing"}
        by_tag = {str(item.get("tag")): item for item in inbounds if isinstance(item, dict) and item.get("tag")}
        if len(by_tag) != len([item for item in inbounds if isinstance(item, dict) and item.get("tag")]): return {"ok": False, "reason": "inbound_tags_must_be_unique"}
        processed: set[str] = set(); updated: set[str] = set(); deleted: set[str] = set(); candidate = copy.deepcopy(config)
        active_core = capability().get("active_core", "none")
        allowed = ALLOWED_XRAY if active_core == "xray" else ALLOWED_SINGBOX if active_core == "sing-box" else set()
        if not allowed: return {"ok": False, "reason": "no_supported_core"}
        for update in updates:
            if not isinstance(update, dict): return {"ok": False, "reason": "invalid_inbound_update"}
            tag = str(update.get("tag", "")).strip()
            if not tag or tag not in by_tag: return {"ok": False, "reason": f"unknown_inbound:{tag}"}
            if tag in processed: return {"ok": False, "reason": f"duplicate_inbound:{tag}"}
            processed.add(tag)
            if bool(update.get("delete", False)):
                candidate["inbounds"] = [item for item in candidate["inbounds"] if not (isinstance(item, dict) and str(item.get("tag")) == tag)]; deleted.add(tag); continue
            protocol = str(update.get("protocol", "")).lower().strip(); transport = str(update.get("transport", "tcp")).lower().strip()
            if protocol not in allowed: return {"ok": False, "reason": f"unsupported_protocol:{protocol}"}
            if transport not in ALLOWED_TRANSPORTS: return {"ok": False, "reason": f"unsupported_transport:{transport}"}
            target = next(item for item in candidate["inbounds"] if isinstance(item, dict) and str(item.get("tag")) == tag)
            if active_core == "xray": _apply_xray(target, protocol, transport)
            else: _apply_singbox(target, protocol, transport)
            updated.add(tag)
        fd, tmp_name = tempfile.mkstemp(prefix="candidate-inbounds-", suffix=".json", dir=ACTIVE.parent); tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(candidate, handle, separators=(",", ":")); handle.flush(); os.fsync(handle.fileno())
            command = ["xray", "run", "-test", "-config", str(tmp)] if active_core == "xray" else ["sing-box", "check", "-c", str(tmp)]
            check = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
            if check.returncode != 0: return {"ok": False, "reason": "config_validation_failed", "detail": (check.stderr or check.stdout)[-1000:]}
            _atomic_copy(ACTIVE, PREVIOUS); _atomic_copy(tmp, ACTIVE)
            service = "xray" if active_core == "xray" else "sing-box"
            restart = subprocess.run(["systemctl", "restart", service], capture_output=True, text=True, timeout=15, check=False)
            if restart.returncode != 0:
                _atomic_copy(PREVIOUS, ACTIVE); subprocess.run(["systemctl", "restart", service], timeout=15, check=False)
                return {"ok": False, "reason": "restart_failed", "rolled_back": True}
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                state = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True, timeout=3, check=False).stdout.strip()
                if state == "active": return {"ok": True, "updated_tags": sorted(updated), "deleted_tags": sorted(deleted), "core": active_core}
                time.sleep(0.25)
            _atomic_copy(PREVIOUS, ACTIVE); subprocess.run(["systemctl", "restart", service], timeout=15, check=False)
            return {"ok": False, "reason": "restart_healthcheck_failed", "rolled_back": True}
        finally:
            tmp.unlink(missing_ok=True)
