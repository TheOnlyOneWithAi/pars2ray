from __future__ import annotations


def test_operations_module_imports() -> None:
    from app.api.operations import router

    paths = {route.path for route in router.routes}
    assert "/api/v1/operations/backup" in paths
    assert "/api/v1/operations/restore" in paths
    assert "/api/v1/operations/telegram/test" in paths
    assert "/api/v1/operations/geo/update" in paths
    assert "/api/v1/operations/fail2ban/status" in paths


def test_control_parity_has_required_surfaces() -> None:
    from app.api.advanced_control import router

    paths = {route.path for route in router.routes}
    required = {
        "/api/v1/control/outbounds/list",
        "/api/v1/control/routing/rules",
        "/api/v1/control/balancers",
        "/api/v1/control/fallbacks",
        "/api/v1/control/capabilities",
    }
    assert required <= paths
