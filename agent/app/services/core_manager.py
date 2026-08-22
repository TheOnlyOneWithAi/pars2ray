from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

STATE = Path(os.getenv("AGENT_STATE_DIR", "/var/lib/pars2ray-agent"))
ACTIVE = STATE / "active.json"
PREVIOUS = STATE / "previous.json"
GOLDEN = STATE / "golden.json"
JOURNAL = STATE / "operations.json"
LOCK = STATE / ".core-manager.lock"
ALLOWED_CORES = ("xray", "sing-box")


def _ensure_state() -> None:
    STATE.mkdir(parents=True, exist_ok=True)


@contextlib.contextmanager
def _state_lock():
    """Serialize config mutations across concurrent API workers/processes."""
    _ensure_state()
    with LOCK.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_copy(source: Path, destination: Path) -> None:
    """Copy a file atomically so readers never see a partial JSON document."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary_path = Path(temporary)
    try:
        os.close(fd)
        shutil.copy2(source, temporary_path)
        with temporary_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        try:
            directory_fd = os.open(destination.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        temporary_path.unlink(missing_ok=True)


def _operation_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_journal() -> dict[str, dict]:
    try:
        data = json.loads(JOURNAL.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_journal(journal: dict[str, dict]) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".operations.", suffix=".tmp", dir=JOURNAL.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(journal, handle, separators=(",", ":"), ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, JOURNAL)
    finally:
        temporary_path.unlink(missing_ok=True)


def _journal_get(operation_id: str, fingerprint: str) -> dict | None:
    if not operation_id:
        return None
    entry = _load_journal().get(operation_id)
    if not entry:
        return None
    if entry.get("fingerprint") != fingerprint:
        raise ValueError("operation_id_reused_with_different_payload")
    result = entry.get("result")
    return result if isinstance(result, dict) else None


def _journal_put(operation_id: str, fingerprint: str, result: dict) -> None:
    if not operation_id:
        return
    journal = _load_journal()
    # Keep the journal bounded while retaining the most recent operations.
    if len(journal) >= 256 and operation_id not in journal:
        for key in list(journal)[:64]:
            journal.pop(key, None)
    journal[operation_id] = {"fingerprint": fingerprint, "result": result}
    _save_journal(journal)


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
            result = subprocess.run([active_core, "version"], capture_output=True, text=True, timeout=3, check=False)
            lines = result.stdout.splitlines()
            version = lines[0][:80] if lines else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            version = "unknown"
    return {"installed": installed, "active_core": active_core, "core_version": version, "protocols": ["vless", "vmess", "trojan", "shadowsocks", "hysteria2"], "transports": ["tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"]}


def core_status() -> dict:
    state = capability()
    active_core = state["active_core"]
    service_state = "NOT_INSTALLED"
    if active_core != "none" and shutil.which("systemctl"):
        try:
            result = subprocess.run(["systemctl", "is-active", active_core], capture_output=True, text=True, timeout=3, check=False)
            service_state = result.stdout.strip() or "UNKNOWN"
        except (OSError, subprocess.TimeoutExpired):
            service_state = "UNKNOWN"
    elif active_core != "none":
        service_state = "UNKNOWN"
    config_metadata = {"present": ACTIVE.exists(), "bytes": ACTIVE.stat().st_size if ACTIVE.exists() else 0, "updated_at": ACTIVE.stat().st_mtime if ACTIVE.exists() else None}
    return {"active_core": active_core, "core_version": state["core_version"], "installed": state["installed"], "service_state": service_state, "config": config_metadata}


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
        result = subprocess.run(["systemctl", "restart", service], capture_output=True, text=True, timeout=15, check=False)
        if result.returncode != 0:
            return False, "restart_failed"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True, timeout=3, check=False).stdout.strip()
            if state == "active":
                return True, "restarted"
            time.sleep(0.25)
        return False, "restart_healthcheck_failed"
    except (OSError, subprocess.TimeoutExpired):
        return False, "restart_failed"


def _restore_service(core: str) -> tuple[bool, str]:
    return _restart(core)


def apply(payload: dict) -> dict:
    """Validate and apply a config with durable idempotency for retried operations."""
    core = payload.get("core", "xray")
    config = payload.get("config")
    operation_id = str(payload.get("operation_id") or payload.get("candidate_id") or "").strip()
    fingerprint = _operation_fingerprint({"core": core, "config": config, "mode": payload.get("mode")})
    if operation_id:
        try:
            with _state_lock():
                cached = _journal_get(operation_id, fingerprint)
                if cached is not None:
                    return cached
        except ValueError as exc:
            return {"ok": False, "reason": str(exc)}

    if core not in ALLOWED_CORES or not isinstance(config, dict):
        result = {"ok": False, "reason": "invalid_config_request"}
        if operation_id:
            with _state_lock():
                _journal_put(operation_id, fingerprint, result)
        return result

    with _state_lock():
        try:
            cached = _journal_get(operation_id, fingerprint)
            if cached is not None:
                return cached
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
                    result = {"ok": False, "reason": reason}
                    _journal_put(operation_id, fingerprint, result)
                    return result

                if had_active:
                    _atomic_copy(ACTIVE, PREVIOUS)
                else:
                    PREVIOUS.unlink(missing_ok=True)

                _atomic_copy(candidate, ACTIVE)
                restarted, restart_reason = _restart(core)
                if not restarted:
                    if had_active and PREVIOUS.exists():
                        _atomic_copy(PREVIOUS, ACTIVE)
                        recovered, recovery_reason = _restore_service(core)
                        result = {"ok": False, "reason": restart_reason, "rolled_back": True, "recovery_ok": recovered, "recovery_reason": recovery_reason}
                    else:
                        ACTIVE.unlink(missing_ok=True)
                        result = {"ok": False, "reason": restart_reason, "rolled_back": True, "recovery_ok": True}
                    _journal_put(operation_id, fingerprint, result)
                    return result

                result = {"ok": True, "core": core, "candidate_id": payload.get("candidate_id", ""), "operation_id": operation_id}
                _journal_put(operation_id, fingerprint, result)
                return result
            finally:
                candidate.unlink(missing_ok=True)
        except Exception:
            raise


def rollback(operation_id: str = "") -> dict:
    """Swap ACTIVE/PREVIOUS once; retries with the same operation ID return the prior result."""
    operation_id = str(operation_id or "").strip()
    fingerprint = hashlib.sha256(b"rollback").hexdigest()
    with _state_lock():
        try:
            cached = _journal_get(operation_id, fingerprint)
            if cached is not None:
                return cached
        except ValueError as exc:
            return {"ok": False, "reason": str(exc)}

        if not PREVIOUS.exists():
            result = {"ok": False, "reason": "no_previous_config"}
            _journal_put(operation_id, fingerprint, result)
            return result

        core = capability().get("active_core")
        if core == "none":
            result = {"ok": False, "reason": "no_supported_core_installed"}
            _journal_put(operation_id, fingerprint, result)
            return result

        current = None
        if ACTIVE.exists():
            fd, current_name = tempfile.mkstemp(prefix="rollback-current-", suffix=".json", dir=STATE)
            os.close(fd)
            current = Path(current_name)
            shutil.copy2(ACTIVE, current)

        try:
            _atomic_copy(PREVIOUS, ACTIVE)
            restarted, reason = _restart(core)
            if not restarted:
                if current and current.exists():
                    _atomic_copy(current, ACTIVE)
                    recovered, recovery_reason = _restore_service(core)
                else:
                    recovered, recovery_reason = False, "no_current_config_to_restore"
                result = {"ok": False, "reason": reason, "rolled_back": True, "recovery_ok": recovered, "recovery_reason": recovery_reason}
                _journal_put(operation_id, fingerprint, result)
                return result

            if current and current.exists():
                _atomic_copy(current, PREVIOUS)
            result = {"ok": True, "rolled_back": True, "core": core, "operation_id": operation_id}
            _journal_put(operation_id, fingerprint, result)
            return result
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
