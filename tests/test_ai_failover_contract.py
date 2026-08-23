from types import SimpleNamespace

import pytest

from app.services.ai_autopilot import AIPolicy
from app.services.ai_failover import on_iran_node_disconnect


@pytest.mark.asyncio
async def test_iran_disconnect_is_ignored_when_autonomous_mode_is_disabled(monkeypatch):
    policy = AIPolicy(level=3, autonomous=False, probe_country="IR", max_nodes=10, max_candidates=5)
    monkeypatch.setattr("app.services.ai_failover.policy", lambda db: policy)
    result = await on_iran_node_disconnect(SimpleNamespace(), SimpleNamespace(country="IR", node_key="IR1"))
    assert result == {"triggered": False, "reason": "ai_autonomous_mode_disabled"}


@pytest.mark.asyncio
async def test_non_iran_disconnect_is_never_an_autonomous_failover(monkeypatch):
    policy = AIPolicy(level=4, autonomous=True, probe_country="IR", max_nodes=10, max_candidates=5)
    monkeypatch.setattr("app.services.ai_failover.policy", lambda db: policy)
    result = await on_iran_node_disconnect(SimpleNamespace(), SimpleNamespace(country="DE", node_key="DE1"))
    assert result == {"triggered": False, "reason": "not_iran_node"}
