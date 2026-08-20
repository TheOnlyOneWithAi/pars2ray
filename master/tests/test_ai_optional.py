import pytest

from app.services import intelligence_cycle


@pytest.mark.asyncio
async def test_cycle_skips_openai_when_ai_disabled(monkeypatch):
    class Settings:
        ai_enabled = False
        openai_api_key = ""
        ai_switch_min_improvement = 10.0
        ai_required_wins = 3
        national_max_candidates_per_round = 10

    monkeypatch.setattr(intelligence_cycle, "settings", Settings())
    monkeypatch.setattr(intelligence_cycle, "build_intelligence_snapshot", lambda: {
        "current_route": {"route_id": "r1", "score": 50},
        "candidates": [{"candidate_id": "c1", "score": 70}],
    })
    monkeypatch.setattr(intelligence_cycle, "golden_candidates", lambda limit=20: [])

    async def fail_if_called(_context):
        raise AssertionError("OpenAI must not be called when AI is disabled")

    monkeypatch.setattr(intelligence_cycle, "analyze", fail_if_called)
    decision = await intelligence_cycle.IntelligenceCycle().run_once()
    assert decision.action == "TEST"
    assert decision.candidate_id == "c1"
