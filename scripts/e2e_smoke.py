from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = os.environ.get("PARS2RAY_E2E_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("ADMIN_USER", "admin")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def request(path: str, method: str = "GET", body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload


def main() -> int:
    status, health = request("/health")
    assert status == 200 and health.get("ok") is True, (status, health)

    status, health_v1 = request("/api/v1/health")
    assert status == 200 and health_v1.get("ok") is True, (status, health_v1)

    status, _ = request("/api/v1/dashboard")
    assert status == 401, status

    if not PASSWORD:
        print("E2E smoke passed (public health + auth boundary; login skipped: ADMIN_PASSWORD unset)")
        return 0

    status, tokens = request("/api/v1/auth/login", "POST", {"username": USERNAME, "password": PASSWORD})
    assert status == 200 and tokens.get("access_token") and tokens.get("refresh_token"), (status, tokens)
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    status, dashboard = request("/api/v1/dashboard", token=access)
    assert status == 200 and isinstance(dashboard, dict), (status, dashboard)

    status, rotated = request("/api/v1/auth/refresh", "POST", {"refresh_token": refresh})
    assert status == 200 and rotated.get("access_token") and rotated.get("refresh_token"), (status, rotated)

    status, _ = request("/api/v1/auth/logout", "POST", {"refresh_token": rotated["refresh_token"]}, token=rotated["access_token"])
    assert status == 200, status

    print("E2E smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
