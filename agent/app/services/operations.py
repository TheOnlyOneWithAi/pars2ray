from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

CORE_SERVICES = {"xray": "xray", "sing-box": "sing-box"}


def _run(command: list[str], timeout: int = 30) -> dict:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": "command_failed", "detail": str(exc)}
    return {"ok": result.returncode == 0, "returncode": result.returncode, "stdout": result.stdout[-8000:], "stderr": result.stderr[-4000:]}


def service_action(action: str) -> dict:
    core = next((name for name in CORE_SERVICES if shutil.which(name)), None)
    if not core:
        return {"ok": False, "reason": "no_supported_core_installed"}
    if not shutil.which("systemctl"):
        return {"ok": False, "reason": "systemctl_not_available"}
    return {"core": core, "action": action, **_run(["systemctl", action, CORE_SERVICES[core]], 30)}


def version() -> dict:
    core = next((name for name in CORE_SERVICES if shutil.which(name)), None)
    if not core:
        return {"ok": False, "reason": "no_supported_core_installed"}
    result = _run([core, "version"], 10)
    result.update({"core": core})
    return result


def logs(lines: int = 200) -> dict:
    if not shutil.which("journalctl"):
        return {"ok": False, "reason": "journalctl_not_available"}
    core = next((name for name in CORE_SERVICES if shutil.which(name)), None)
    if not core:
        return {"ok": False, "reason": "no_supported_core_installed"}
    bounded = max(1, min(int(lines), 2000))
    result = _run(["journalctl", "-u", core, "-n", str(bounded), "--no-pager", "-o", "short-iso"], 20)
    return {"core": core, "lines": bounded, **result}


def update() -> dict:
    # The node agent is upgraded by the master over its authenticated SSH path.
    # This operation refreshes the installed proxy core only when the platform
    # package already exposes a supported updater; it never executes a remote
    # URL or arbitrary user-provided command.
    core = next((name for name in CORE_SERVICES if shutil.which(name)), None)
    if not core:
        return {"ok": False, "reason": "no_supported_core_installed"}
    if core == "xray":
        return {"ok": False, "reason": "core_update_requires_managed_release"}
    return {"ok": False, "reason": "core_update_requires_managed_release"}


def firewall_status() -> dict:
    for command in (["ufw", "status"], ["firewall-cmd", "--state"]):
        if shutil.which(command[0]):
            return {"command": command[0], **_run(command, 15)}
    return {"ok": False, "reason": "supported_firewall_not_found"}
