from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_node_actions_match_backend_routes() -> None:
    source = (ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    assert "`/api/v1/nodes/${encodeURIComponent(nodeKey)}/rollback`" in source
    assert "/api/v1/node-management/${encodeURIComponent(nodeKey)}/rollback" not in source


def test_frontend_update_node_has_no_operator_endpoint_field() -> None:
    source = (ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    assert "payload:{country?:string;endpoint?:string" not in source
