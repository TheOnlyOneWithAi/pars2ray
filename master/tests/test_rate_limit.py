from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.services.rate_limit as rate_limit


def test_fallback_rate_limit_without_redis(monkeypatch):
    monkeypatch.setattr(rate_limit, "_redis", lambda: None)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_per_minute", 1)
    rate_limit._events.clear()
    request = SimpleNamespace(client=SimpleNamespace(host="ci-test-client"))

    rate_limit.enforce(request)

    with pytest.raises(HTTPException) as exc_info:
        rate_limit.enforce(request)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "rate_limit_exceeded"
