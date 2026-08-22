import importlib.util
import json


CORE_PATH = __import__("pathlib").Path(__file__).parents[1] / "agent" / "app" / "services" / "core_manager.py"
SPEC = importlib.util.spec_from_file_location("pars2ray_agent_core_manager_tests", CORE_PATH)
assert SPEC and SPEC.loader
core_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core_manager)


def setup_state(tmp_path, monkeypatch):
    monkeypatch.setattr(core_manager, "STATE", tmp_path)
    monkeypatch.setattr(core_manager, "ACTIVE", tmp_path / "active.json")
    monkeypatch.setattr(core_manager, "PREVIOUS", tmp_path / "previous.json")
    monkeypatch.setattr(core_manager, "GOLDEN", tmp_path / "golden.json")
    monkeypatch.setattr(core_manager, "JOURNAL", tmp_path / "operations.json")
    monkeypatch.setattr(core_manager, "LOCK", tmp_path / ".core-manager.lock")


def test_apply_validation_failure_never_touches_active(tmp_path, monkeypatch):
    setup_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text('{"old":true}', encoding="utf-8")
    monkeypatch.setattr(core_manager, "_validate", lambda *_: (False, "bad_config"))

    result = core_manager.apply({"core": "xray", "config": {"new": True}})

    assert result == {"ok": False, "reason": "bad_config"}
    assert json.loads(core_manager.ACTIVE.read_text()) == {"old": True}
    assert not core_manager.PREVIOUS.exists()


def test_apply_restart_failure_restores_config_and_restarts_old(tmp_path, monkeypatch):
    setup_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text('{"old":true}', encoding="utf-8")
    monkeypatch.setattr(core_manager, "_validate", lambda *_: (True, "validated"))
    restarts = iter([(False, "restart_failed"), (True, "recovered")])
    monkeypatch.setattr(core_manager, "_restart", lambda *_: next(restarts))

    result = core_manager.apply({"core": "xray", "config": {"new": True}})

    assert result["ok"] is False
    assert result["rolled_back"] is True
    assert result["recovery_ok"] is True
    assert json.loads(core_manager.ACTIVE.read_text()) == {"old": True}


def test_apply_failed_restart_is_retryable(tmp_path, monkeypatch):
    setup_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text('{"old":true}', encoding="utf-8")
    monkeypatch.setattr(core_manager, "_validate", lambda *_: (True, "validated"))
    restarts = iter([(False, "restart_failed"), (True, "recovered"), (True, "restarted")])
    monkeypatch.setattr(core_manager, "_restart", lambda *_: next(restarts))
    payload = {"core": "xray", "config": {"new": True}, "operation_id": "retry-me"}

    first = core_manager.apply(payload)
    second = core_manager.apply(payload)

    assert first["ok"] is False
    assert second["ok"] is True
    assert second["operation_id"] == "retry-me"


def test_successful_apply_is_idempotent(tmp_path, monkeypatch):
    setup_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text('{"old":true}', encoding="utf-8")
    monkeypatch.setattr(core_manager, "_validate", lambda *_: (True, "validated"))
    calls = []
    monkeypatch.setattr(core_manager, "_restart", lambda *_: calls.append(1) or (True, "restarted"))
    payload = {"core": "xray", "config": {"new": True}, "operation_id": "same-op"}

    first = core_manager.apply(payload)
    second = core_manager.apply(payload)

    assert first == second
    assert len(calls) == 1


def test_operation_id_reuse_with_different_payload_is_rejected(tmp_path, monkeypatch):
    setup_state(tmp_path, monkeypatch)
    monkeypatch.setattr(core_manager, "_validate", lambda *_: (True, "validated"))
    monkeypatch.setattr(core_manager, "_restart", lambda *_: (True, "restarted"))

    first = core_manager.apply({"core": "xray", "config": {"a": 1}, "operation_id": "same-op"})
    second = core_manager.apply({"core": "xray", "config": {"a": 2}, "operation_id": "same-op"})

    assert first["ok"] is True
    assert second == {"ok": False, "reason": "operation_id_reused_with_different_payload"}


def test_apply_first_config_restart_failure_removes_candidate(tmp_path, monkeypatch):
    setup_state(tmp_path, monkeypatch)
    monkeypatch.setattr(core_manager, "_validate", lambda *_: (True, "validated"))
    monkeypatch.setattr(core_manager, "_restart", lambda *_: (False, "restart_failed"))

    result = core_manager.apply({"core": "xray", "config": {"new": True}})

    assert result["ok"] is False
    assert result["rolled_back"] is True
    assert result["recovery_ok"] is True
    assert not core_manager.ACTIVE.exists()


def test_rollback_restart_failure_restores_running_config(tmp_path, monkeypatch):
    setup_state(tmp_path, monkeypatch)
    core_manager.ACTIVE.write_text('{"current":true}', encoding="utf-8")
    core_manager.PREVIOUS.write_text('{"previous":true}', encoding="utf-8")
    monkeypatch.setattr(core_manager, "capability", lambda: {"active_core": "xray"})
    restarts = iter([(False, "restart_failed"), (True, "recovered")])
    monkeypatch.setattr(core_manager, "_restart", lambda *_: next(restarts))

    result = core_manager.rollback()

    assert result["ok"] is False
    assert result["recovery_ok"] is True
    assert json.loads(core_manager.ACTIVE.read_text()) == {"current": True}
    assert json.loads(core_manager.PREVIOUS.read_text()) == {"previous": True}


def test_rollback_without_previous_is_retryable_after_previous_appears(tmp_path, monkeypatch):
    setup_state(tmp_path, monkeypatch)
    monkeypatch.setattr(core_manager, "capability", lambda: {"active_core": "xray"})
    monkeypatch.setattr(core_manager, "_restart", lambda *_: (True, "restarted"))

    first = core_manager.rollback("rollback-retry")
    core_manager.ACTIVE.write_text('{"current":true}', encoding="utf-8")
    core_manager.PREVIOUS.write_text('{"previous":true}', encoding="utf-8")
    second = core_manager.rollback("rollback-retry")

    assert first == {"ok": False, "reason": "no_previous_config"}
    assert second["ok"] is True
