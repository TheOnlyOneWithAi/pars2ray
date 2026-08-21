from app.api.node_management import NodeProvisionRequest, SSHRequest


def test_node_provision_does_not_require_endpoint() -> None:
    payload = NodeProvisionRequest(
        node_key="DE1",
        country="de",
        ssh=SSHRequest(host="203.0.113.10", username="root", password="secret"),
    )

    assert payload.node_key == "DE1"
    assert payload.country == "DE"
    assert payload.ssh.host == "203.0.113.10"
    assert "endpoint" not in NodeProvisionRequest.model_fields


def test_ssh_contract_does_not_require_fingerprint() -> None:
    payload = SSHRequest(host="203.0.113.10", username="root", password="secret")

    assert payload.host_key_fingerprint if hasattr(payload, "host_key_fingerprint") else True
    assert payload.to_config().host_key_fingerprint is None
