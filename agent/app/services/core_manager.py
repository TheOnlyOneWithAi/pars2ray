from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

STATE = Path(os.getenv("AGENT_STATE_DIR", "/var/lib/pars2ray-agent"))
ACTIVE = STATE / "active.json"
PREVIOUS = STATE / "previous.json"
GOLDEN = STATE / "golden.json"
ALLOWED_CORES = {"xray", "sing-box"}


def _ensure_state() -> None:
    STATE.mkdir(parents=True, exist_ok=True)


def capability() -> dict:
    installed = {core: bool(shutil.which(core)) for core in ALLOWED_CORES}
    active_core = next((core for core, found in installed.items() if found), "none")
    version = ""
    if active_core != "none":
        try:
            version = subprocess.run([active_core, "version"], capture_output=True, text=True, timeout=3, check=False).stdout.splitlines()[0][:80]
        except (OSError, IndexError, subprocess.TimeoutExpired):
            version = "unknown"
    return {"installed": installed, "active_core": active_core, "core_version": version, "protocols": ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"], "transports": ["tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"]}


def core_status() -> dict:
    """Return fixed, non-shell core diagnostics for the Master panel."""
    state = capability()
    active_core = state["active_core"]
    service_state = "NOT_INSTALLED"
    if active_core != "none":
        service = active_core
        if shutil.which("systemctl"):
            try:
                result = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True, timeout=3, check=False)
                service_state = result.stdout.strip() or "UNKNOWN"
            except (OSError, subprocess.TimeoutExpired):
                service_state = "UNKNOWN"
        else:
            service_state = "UNKNOWN"
    config_metadata = {"present": ACTIVE.exists(), "bytes": ACTIVE.stat().st_size if ACTIVE.exists() else 0, "updated_at": ACTIVE.stat().st_mtime if ACTIVE.exists() else None}
    return {"active_core": active_core, "core_version": state["core_version"], "installed": state["installed"], "service_state": service_state, "config": config_metadata}


def _validate(core: str) -> tuple[bool, str]:
    if core == "xray":
        command = ["xray", "run", "-test", "-config", str(ACTIVE)]
    elif core == "sing-box":
        command = ["sing-box", "check", "-c", str(ACTIVE)]
    else:
        return False, "unsupported_core"
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        return result.returncode == 0, "validated" if result.returncode == 0 else "config_validation_failed"
    except (OSError, subprocess.TimeoutExpired):
        return False, "core_validation_failed"


def _restart(core: str) -> tuple[bool, str]:
    service = "xray" if core == "xray" else "sing-box" if core == "sing-box" else ""
    if not service:
        return False, "unsupported_core"
    try:
        result = subprocess.run(["systemctl", "restart", service], capture_output=True, text=True, timeout=15, check=False)
        return result.returncode == 0, "restarted" if result.returncode == 0 else "restart_failed"
    except (OSError, subprocess.TimeoutExpired):
        return False, "restart_failed"


def apply(payload: dict) -> dict:
    _ensure_state()
    core = payload.get("core", "xray")
    config = payload.get("config")
    if core not in ALLOWED_CORES or not isinstance(config, dict):
        return {"ok": False, "reason": "invalid_config_request"}
    tmp = STATE / "candidate.json"
    tmp.write_text(json.dumps(config, separators=(",", ":")), encoding="utf-8")
    if ACTIVE.exists():
        shutil.copy2(ACTIVE, PREVIOUS)
    shutil.copy2(tmp, ACTIVE)
    valid, reason = _validate(core)
    if not valid:
        if PREVIOUS.exists():
            shutil.copy2(PREVIOUS, ACTIVE)
        return {"ok": False, "reason": reason}
    restarted, restart_reason = _restart(core)
    if not restarted:
        if PREVIOUS.exists():
            shutil.copy2(PREVIOUS, ACTIVE)
        return {"ok": False, "reason": restart_reason}
    return {"ok": True, "core": core, "candidate_id": payload.get("candidate_id", "")}


def rollback() -> dict:
    _ensure_state()
    if not PREVIOUS.exists():
        return {"ok": False, "reason": "no_previous_config"}
    shutil.copy2(PREVIOUS, ACTIVE)
    return {"ok": True, "rolled_back": True}


def restart_service() -> dict:
    core = capability().get("active_core")
    if core == "none":
        return {"ok": False, "reason": "no_supported_core_installed"}
    ok, reason = _restart(core)
    return {"ok": ok, "reason": reason, "core": core}


def mark_golden() -> dict:
    _ensure_state()
    if not ACTIVE.exists():
        return {"ok": False, "reason": "no_active_config"}
    shutil.copy2(ACTIVE, GOLDEN)
    return {"ok": True}
