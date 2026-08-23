from __future__ import annotations

from pathlib import Path

from app.api.node_management import NodeProvisionRequest, NodeUpdateRequest


ROOT = Path(__file__).resolve().parents[1]


def test_node_creation_is_ssh_only() -> None:
    assert set(NodeProvisionRequest.model_fields) == {"node_key", "country", "ssh"}


def test_node_update_cannot_accept_operator_endpoint() -> None:
    assert "endpoint" not in NodeUpdateRequest.model_fields


def test_node_ui_does_not_expose_agent_endpoint() -> None:
    source = (ROOT / "frontend/src/NodeProvisionPage.tsx").read_text(encoding="utf-8")
    assert "Agent endpoint" not in source
    assert "endpoint:" not in source
