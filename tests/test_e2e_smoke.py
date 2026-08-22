from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _prepare_database() -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT / "master"))
    subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


_prepare_database()

from app.main import app  # noqa: E402


def test_health_and_security_headers() -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"Host": "localhost"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_database_readiness() -> None:
    with TestClient(app) as client:
        response = client.get("/ready", headers={"Host": "localhost"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["database"] == "ready"


def test_removed_legacy_api_surface_is_not_exposed() -> None:
    with TestClient(app) as client:
        for path in ("/api/v1/routes", "/api/v1/plans", "/api/v1/optimizer"):
            response = client.get(path, headers={"Host": "localhost"})
            assert response.status_code == 404, path


def test_subscription_api_is_exposed() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/subscriptions", headers={"Host": "localhost"})
    assert response.status_code == 401
