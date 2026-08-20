import app.services.rate_limit as rate_limit


def test_fallback_rate_limit(monkeypatch, client):
    monkeypatch.setattr(rate_limit, "_redis", lambda: None)
    rate_limit._events.clear()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
