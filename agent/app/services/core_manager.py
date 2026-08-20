from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

STATE = Path(os.getenv("AGENT_STATE_DIR", "/var/lib/pars2ray-agent"))
ACTIVE = STATE / "active.json"
PREVIOUS = STATE / "previous.json"
GOLDEN = STATE / "golden.json"
ALLOWED_CORES = ("xray", "sing-box")


def _ensure_state() -> None:
    STATE.mkdir(parents=True, exist_ok=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    """Copy a file atomically so readers never see a partial JSON document."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        os.close(fd)
        temporary_path = Path(temporary)
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def capability() -> dict:
    installed = {core: bool(shutil.which(core)) for core in ALLOWED_CORES}
    preferred = os.getenv("PARS2RAY_CORE", "").strip()
    if preferred in installed and installed[preferred]:
        active_core = preferred
    else:
        active_core = next((core for core in ALLOWED_CORES if installed[core]), "none")

    version = ""
    if active_core != "none":
        try:
            result = subprocess.run(
                [active_core, "version"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            version = result.stdout.splitlines()[0][:80] if result.stdout.splitlines() else "unknown"
        except (OSError, IndexError, subprocess.TimeoutExpired):
            version = "unknown"
    return {
        "installed": installed,
        "active_core": active_core,
        "core_version": version,
        "protocols": ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"],
        "transports": ["tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"],
    }


def core_status() -> dict:
    """Return fixed, non-shell core diagnostics for the Master panel."""
    state = capability()
    active_core = state["active_core"]
    service_state = "NOT_INSTALLED"
    if active_core != "none":
        if shutil.which("systemctl"):
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", active_core],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                service_state = result.stdout.strip() or "UNKNOWN"
            except (OSError, subprocess.TimeoutExpired):
                service_state = "UNKNOWN"
        else:
            service_state = "UNKNOWN"
    config_metadata = {
        "present": ACTIVE.exists(),
        "bytes": ACTIVE.stat().st_size if ACTIVE.exists() else 0,
        "updated_at": ACTIVE.stat().st_mtime if ACTIVE.exists() else None,
    }
    return {
        "active_core": active_core,
        "core_version": state["core_version"],
        "installed": state["installed"],
        "service_state": service_state,
        "config": config_metadata,
    }


def _validate(core: str, config_path: Path = ACTIVE) -> tuple[bool, str]:
    if core == "xray":
        command = ["xray", "run", "-test", "-config", str(config_path)]
    elif core == "sing-box":
        command = ["sing-box", "check", "-c", str(config_path)]
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
    if not shutil.which("systemctl"):
        return False, "systemctl_not_available"
    try:
        result = subprocess.run(
            ["systemctl", "restart", service],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return result.returncode == 0, "restarted" if result.returncode == 0 else "restart_failed"
    except (OSError, subprocess.TimeoutExpired):
        return False, "restart_failed"


def apply(payload: dict) -> dict:
    """Validate and apply a config without leaving an untested config behind on failure."""
    _ensure_state()
    core = payload.get("core", "xray")
    config = payload.get("config")
    if core not in ALLOWED_CORES or not isinstance(config, dict):
        return {"ok": False, "reason": "invalid_config_request"}

    fd, candidate_name = tempfile.mkstemp(prefix="candidate-", suffix=".json", dir=STATE)
    candidate = Path(candidate_name)
    had_active = ACTIVE.exists()
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())

        valid, reason = _validate(core, candidate)
        if not valid:
            return {"ok": False, "reason": reason}

        # Only create a rollback point from the actual active config. Never use
        # an old PREVIOUS file when there was no active config before this apply.
        if had_active:
            _atomic_copy(ACTIVE, PREVIOUS)

        _atomic_copy(candidate, ACTIVE)
        restarted, restart_reason = _restart(core)
        if not restarted:
            if had_active and PREVIOUS.exists():
                _atomic_copy(PREVIOUS, ACTIVE)
            else:
                try:
                    ACTIVE.unlink()
                except FileNotFoundError:
                    pass
            return {"ok": False, "reason": restart_reason, "rolled_back": True}

        return {"ok": True, "core": core, "candidate_id": payload.get("candidate_id", "")}
    finally:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def rollback() -> dict:
    """Swap ACTIVE/PREVIOUS and restart the selected core; restore on failure."""
    _ensure_state()
    if not PREVIOUS.exists():
        return {"ok": False, "reason": "no_previous_config"}

    core = capability().get("active_core")
    if core == "none":
        return {"ok": False, "reason": "no_supported_core_installed"}

    current = None
    if ACTIVE.exists():
        fd, current_name = tempfile.mkstemp(prefix="rollback-current-", suffix=".json", dir=STATE)
        os.close(fd)
        current = Path(current_name)
        try:
            shutil.copy2(ACTIVE, current)
        except Exception:
            current.unlink(missing_ok=True)
            raise

    try:
        _atomic_copy(PREVIOUS, ACTIVE)
        restarted, reason = _restart(core)
        if not restarted:
            if current and current.exists():
                _atomic_copy(current, ACTIVE)
            return {"ok": False, "reason": reason, "rolled_back": True}

        if current and current.exists():
            _atomic_copy(current, PREVIOUS)
        return {"ok": True, "rolled_back": True, "core": core}
    finally:
        if current:
            current.unlink(missing_ok=True)


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
    _atomic_copy(ACTIVE, GOLDEN)
    return {"ok": True}
