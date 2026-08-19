import importlib.util
from pathlib import Path


CORE_PATH = Path(__file__).parents[1] / "agent" / "app" / "services" / "core_manager.py"
SPEC = importlib.util.spec_from_file_location("pars2ray_agent_core_manager", CORE_PATH)
assert SPEC and SPEC.loader
core_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core_manager)


def test_core_status_returns_redacted_diagnostics(monkeypatch):
    monkeypatch.setattr(core_manager.shutil, "which", lambda _: None)

    result = core_manager.core_status()

    assert result["active_core"] == "none"
    assert result["service_state"] == "NOT_INSTALLED"
    assert result["config"]["present"] is False
    assert "config_path" not in result
