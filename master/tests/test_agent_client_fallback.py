import pytest
import httpx

from app.services import agent_client


class FakeNode:
    endpoint = "http://203.0.113.10:9100"
    agent_token_enc = "encrypted-token"
    ssh_config_enc = "encrypted-ssh"


@pytest.mark.asyncio
async def test_request_falls_back_to_ssh_on_transport_failure(monkeypatch):
    calls = []

    async def fake_ssh_request(node, method, path, json_data=None):
        calls.append((node, method, path, json_data))
        return {"ok": True, "transport": "ssh"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def request(self, *args, **kwargs):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(agent_client, "_ssh_request", fake_ssh_request)
    monkeypatch.setattr(agent_client.httpx, "AsyncClient", lambda **_: Client())
    monkeypatch.setattr(agent_client, "decrypt_secret", lambda value: "token")

    result = await agent_client.request(FakeNode(), "POST", "/command", {"command": "GET_STATUS"})

    assert result == {"ok": True, "transport": "ssh"}
    assert calls[0][1:] == ("POST", "/command", {"command": "GET_STATUS"})


@pytest.mark.asyncio
async def test_request_does_not_hide_agent_auth_failure(monkeypatch):
    class Response:
        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "unauthorized",
                request=httpx.Request("POST", "http://node/command"),
                response=httpx.Response(401),
            )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def request(self, *args, **kwargs):
            return Response()

    fallback_called = False

    async def fake_ssh_request(*args, **kwargs):
        nonlocal fallback_called
        fallback_called = True
        return {"ok": True}

    monkeypatch.setattr(agent_client, "_ssh_request", fake_ssh_request)
    monkeypatch.setattr(agent_client.httpx, "AsyncClient", lambda **_: Client())
    monkeypatch.setattr(agent_client, "decrypt_secret", lambda value: "token")

    with pytest.raises(httpx.HTTPStatusError):
        await agent_client.request(FakeNode(), "POST", "/command", {})

    assert fallback_called is False
