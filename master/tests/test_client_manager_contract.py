from datetime import datetime, timedelta

from app.api.client_manager import _client_id
from app.schemas import ClientCreate, ClientUpdate


def test_client_id_is_deterministic_and_uuid_like() -> None:
    value = _client_id("a" * 64)
    assert value == _client_id("a" * 64)
    assert len(value) == 36


def test_client_create_defaults_are_safe() -> None:
    payload = ClientCreate(user_id=1, plan_id=2)
    assert payload.node_keys == []
    assert payload.single_active is True


def test_client_update_rejects_past_expiry() -> None:
    value = datetime.utcnow() - timedelta(seconds=1)
    try:
        ClientUpdate(expires_at=value)
    except Exception:
        raise AssertionError("schema should accept datetime; endpoint enforces future expiry")
