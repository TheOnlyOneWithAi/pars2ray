from fastapi.testclient import TestClient

from app.main import app


def test_health_and_security_headers() -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"Host": "localhost"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_removed_legacy_api_surface_is_not_exposed() -> None:
    with TestClient(app) as client:
        for path in ("/api/v1/routes", "/api/v1/plans", "/api/v1/subscriptions", "/api/v1/optimizer"):
            response = client.get(path, headers={"Host": "localhost"})
            assert response.status_code == 404, path
