import inspect

from app.api.node_management import NodeProvisionRequest, SSHRequest, update_node


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

    assert payload.to_config().host_key_fingerprint is None


def test_ssh_update_reprovisions_before_switching_management_target() -> None:
    """Changing SSH must install the same agent token on the new target first."""
    source = inspect.getsource(update_node)
    provision_call = source.index("provision_over_ssh(ssh_config, node.node_key, country, agent_token)")
    endpoint_switch = source.index("node.endpoint = f\"http://{payload.ssh.host}:9100\"")
    assert provision_call < endpoint_switch
    assert "node_reprovision_failed" in source
    assert "decrypt_secret(node.agent_token_enc)" in source
