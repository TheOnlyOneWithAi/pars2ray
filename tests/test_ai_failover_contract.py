from types import SimpleNamespace

import pytest

from app.services.ai_autopilot import AIPolicy
from app.services.ai_failover import on_iran_node_disconnect


def make_policy(**overrides):
    values = {
        "enabled": True,
        "level": 4,
        "autonomous": True,
        "failover_on_iran_disconnect": True,
        "probe_country": "IR",
        "max_nodes": 10,
        "max_candidates": 5,
    }
    values.update(overrides)
    return AIPolicy(**values)


@pytest.mark.asyncio
async def test_iran_disconnect_is_ignored_when_autonomous_mode_is_disabled(monkeypatch):
    policy = make_policy(level=3, autonomous=False)
    monkeypatch.setattr("app.services.ai_failover.policy", lambda db: policy)
    result = await on_iran_node_disconnect(
        SimpleNamespace(),
        SimpleNamespace(country="IR", node_key="IR1"),
    )
    assert result == {"triggered": False, "reason": "ai_autonomous_mode_disabled"}


@pytest.mark.asyncio
async def test_iran_disconnect_respects_explicit_failover_switch(monkeypatch):
    policy = make_policy(failover_on_iran_disconnect=False)
    monkeypatch.setattr("app.services.ai_failover.policy", lambda db: policy)
    result = await on_iran_node_disconnect(
        SimpleNamespace(),
        SimpleNamespace(country="IR", node_key="IR1"),
    )
    assert result == {"triggered": False, "reason": "iran_failover_disabled"}


@pytest.mark.asyncio
async def test_non_iran_disconnect_is_never_an_autonomous_failover(monkeypatch):
    policy = make_policy()
    monkeypatch.setattr("app.services.ai_failover.policy", lambda db: policy)
    result = await on_iran_node_disconnect(
        SimpleNamespace(),
        SimpleNamespace(country="DE", node_key="DE1"),
    )
    assert result == {"triggered": False, "reason": "not_iran_node"}
