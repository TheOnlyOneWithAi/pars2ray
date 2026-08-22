from datetime import timedelta

import pytest

from app.core.security import utcnow
from app.schemas import ClientCreate, UserCreate


def test_user_create_accepts_subscription_provisioning_fields() -> None:
    payload = UserCreate(
        username="alice",
        email="alice@example.com",
        password="a" * 12,
        role="USER",
        plan_id=1,
        node_keys=["US1", "DE1"],
        expires_at=utcnow() + timedelta(days=30),
    )
    assert payload.plan_id == 1
    assert payload.node_keys == ["US1", "DE1"]
    assert payload.expires_at is not None


def test_user_create_rejects_invalid_plan_id() -> None:
    with pytest.raises(ValueError):
        UserCreate(username="alice", password="a" * 12, plan_id=0)


def test_client_create_rejects_invalid_plan_id() -> None:
    with pytest.raises(ValueError):
        ClientCreate(user_id=1, plan_id=0)


def test_client_create_preserves_explicit_expiry() -> None:
    expires = utcnow() + timedelta(days=7)
    payload = ClientCreate(user_id=1, plan_id=1, expires_at=expires)
    assert payload.expires_at == expires
