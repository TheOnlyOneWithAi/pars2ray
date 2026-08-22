import json

from app.services import core_manager


def _fake_restart_factory(states):
    calls = []

    def fake_restart(core):
        calls.append(core)
        return states.pop(0)

    return fake_restart, calls


def _patch_state(tmp_path, monkeypatch):
    monkeypatch.setattr(core_manager, "STATE", tmp_path)
    monkeypatch.setattr(core_manager, "ACTIVE", tmp_path / "active.json")
    monkeypatch.setattr(core_manager, "PREVIOUS", tmp_path / "previous.json")
    monkeypatch.setattr(core_manager, "JOURNAL", tmp_path / "operations.json")
    monkeypatch.setattr(core_manager, "LOCK", tmp_path / ".lock")


def test_apply_rejects_invalid_core(tmp_path, monkeypatch):
    _patch_state(tmp_path, monkeypatch)
    result = core_manager.apply({"core": "evil", "config": {}})
    assert result == {"ok": False, "reason": "invalid_config_request"}


def test_apply_validation_failure_does_not_replace_active(tmp_path, monkeypatch):
    _patch_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text(json.dumps({"good": True}), encoding="utf-8")
    monkeypatch.setattr(core_manager, "_validate", lambda core, path: (False, "bad_config"))
    result = core_manager.apply({"core": "xray", "config": {"bad": True}})
    assert result["ok"] is False
    assert result["reason"] == "bad_config"
    assert json.loads(core_manager.ACTIVE.read_text(encoding="utf-8")) == {"good": True}
    assert not core_manager.PREVIOUS.exists()


def test_apply_restart_failure_restores_previous_and_service(tmp_path, monkeypatch):
    _patch_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text(json.dumps({"version": 1}), encoding="utf-8")
    monkeypatch.setattr(core_manager, "_validate", lambda core, path: (True, "validated"))
    fake_restart, calls = _fake_restart_factory([(False, "restart_failed"), (True, "recovered")])
    monkeypatch.setattr(core_manager, "_restart", fake_restart)
    result = core_manager.apply({"core": "xray", "config": {"version": 2}})
    assert result["ok"] is False
    assert result["rolled_back"] is True
    assert result["recovery_ok"] is True
    assert calls == ["xray", "xray"]
    assert json.loads(core_manager.ACTIVE.read_text(encoding="utf-8")) == {"version": 1}
    assert json.loads(core_manager.PREVIOUS.read_text(encoding="utf-8")) == {"version": 1}


def test_rollback_failure_restores_current_config(tmp_path, monkeypatch):
    _patch_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text(json.dumps({"version": 2}), encoding="utf-8")
    core_manager.PREVIOUS.write_text(json.dumps({"version": 1}), encoding="utf-8")
    monkeypatch.setattr(core_manager, "capability", lambda: {"active_core": "xray"})
    fake_restart, calls = _fake_restart_factory([(False, "restart_failed"), (True, "recovered")])
    monkeypatch.setattr(core_manager, "_restart", fake_restart)
    result = core_manager.rollback("rollback-test")
    assert result["ok"] is False
    assert result["recovery_ok"] is True
    assert calls == ["xray", "xray"]
    assert json.loads(core_manager.ACTIVE.read_text(encoding="utf-8")) == {"version": 2}
    assert json.loads(core_manager.PREVIOUS.read_text(encoding="utf-8")) == {"version": 1}


def test_capability_version_failure_is_non_fatal(monkeypatch):
    monkeypatch.setattr(core_manager.shutil, "which", lambda name: "/usr/bin/xray" if name == "xray" else None)

    def fail(*args, **kwargs):
        raise OSError("missing binary")

    monkeypatch.setattr(core_manager.subprocess, "run", fail)
    result = core_manager.capability()
    assert result["active_core"] == "xray"
    assert result["core_version"] == "unknown"


def test_apply_operation_is_idempotent(tmp_path, monkeypatch):
    _patch_state(tmp_path, monkeypatch)
    monkeypatch.setattr(core_manager, "_validate", lambda core, path: (True, "validated"))
    calls = []

    def fake_restart(core):
        calls.append(core)
        return True, "restarted"

    monkeypatch.setattr(core_manager, "_restart", fake_restart)
    payload = {"core": "xray", "config": {"version": 3}, "operation_id": "apply-1"}
    first = core_manager.apply(payload)
    second = core_manager.apply(payload)
    assert first == second
    assert calls == ["xray"]


def test_operation_id_cannot_be_reused_with_different_payload(tmp_path, monkeypatch):
    _patch_state(tmp_path, monkeypatch)
    monkeypatch.setattr(core_manager, "_validate", lambda core, path: (True, "validated"))
    monkeypatch.setattr(core_manager, "_restart", lambda core: (True, "restarted"))
    assert core_manager.apply({"core": "xray", "config": {"version": 1}, "operation_id": "same"})["ok"] is True
    result = core_manager.apply({"core": "xray", "config": {"version": 2}, "operation_id": "same"})
    assert result == {"ok": False, "reason": "operation_id_reused_with_different_payload"}


def test_rollback_operation_is_idempotent(tmp_path, monkeypatch):
    _patch_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text(json.dumps({"version": 2}), encoding="utf-8")
    core_manager.PREVIOUS.write_text(json.dumps({"version": 1}), encoding="utf-8")
    monkeypatch.setattr(core_manager, "capability", lambda: {"active_core": "xray"})
    calls = []
    monkeypatch.setattr(core_manager, "_restart", lambda core: (calls.append(core) or True, "restarted"))
    first = core_manager.rollback("rollback-1")
    second = core_manager.rollback("rollback-1")
    assert first == second
    assert calls == ["xray"]
