import pytest

from app.services import intelligence_cycle


class Settings:
    ai_enabled = False
    openai_api_key = ""
    ai_switch_min_improvement = 10.0
    ai_required_wins = 3
    national_max_candidates_per_round = 10


@pytest.mark.asyncio
async def test_cycle_skips_openai_when_ai_disabled(monkeypatch):
    monkeypatch.setattr(intelligence_cycle, "settings", Settings())
    monkeypatch.setattr(intelligence_cycle, "build_intelligence_snapshot", lambda: {
        "current_route": {"route_id": "r1", "score": 50},
        "current_score": 50,
        "candidates": [{"candidate_id": "c1", "score": 70}],
    })

    async def fail_if_called(_context):
        raise AssertionError("OpenAI must not be called when AI is disabled")

    monkeypatch.setattr(intelligence_cycle, "analyze", fail_if_called)
    decision = await intelligence_cycle.IntelligenceCycle().run_once()
    assert decision.action == "TEST"
    assert decision.candidate_id == "c1"


@pytest.mark.asyncio
async def test_ai_cannot_select_unknown_candidate(monkeypatch):
    class EnabledSettings(Settings):
        ai_enabled = True
        openai_api_key = "configured"

    monkeypatch.setattr(intelligence_cycle, "settings", EnabledSettings())
    monkeypatch.setattr(intelligence_cycle, "build_intelligence_snapshot", lambda: {
        "current_route": {"route_id": "r1", "score": 50},
        "current_score": 50,
        "candidates": [{"candidate_id": "c1", "score": 70}],
    })
    monkeypatch.setattr(intelligence_cycle, "analyze", lambda _context: None)

    async def fake_analyze(_context):
        return ({"action": "SWITCH", "candidate_id": "does-not-exist", "reason": "bad"}, {})

    monkeypatch.setattr(intelligence_cycle, "analyze", fake_analyze)
    decision = await intelligence_cycle.IntelligenceCycle().run_once()
    assert decision.action == "KEEP"
    assert decision.candidate_id is None


@pytest.mark.asyncio
async def test_ai_cannot_canary_non_improving_candidate(monkeypatch):
    class EnabledSettings(Settings):
        ai_enabled = True
        openai_api_key = "configured"

    monkeypatch.setattr(intelligence_cycle, "settings", EnabledSettings())
    monkeypatch.setattr(intelligence_cycle, "build_intelligence_snapshot", lambda: {
        "current_route": {"route_id": "r1", "score": 50},
        "current_score": 50,
        "candidates": [{"candidate_id": "c1", "score": 50}],
    })

    async def fake_analyze(_context):
        return ({"action": "CANARY", "candidate_id": "c1", "reason": "bad"}, {})

    monkeypatch.setattr(intelligence_cycle, "analyze", fake_analyze)
    decision = await intelligence_cycle.IntelligenceCycle().run_once()
    assert decision.action == "KEEP"
    assert decision.candidate_id == "c1"
