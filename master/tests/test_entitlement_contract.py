from datetime import datetime, timedelta, timezone

from app.schemas import ClientCreate, ClientOut, ClientUpdate, PlanCreate, UserCreate, UserUpdate


def test_user_limits_allow_unlimited_without_inbound_or_plan():
    payload = UserCreate(username="plain-user", quota_gb=0, duration_days=0)
    assert payload.plan_id is None
    assert payload.inbound_ids == []
    assert payload.quota_gb == 0
    assert payload.duration_days == 0


def test_user_limit_update_supports_unlimited_values():
    payload = UserUpdate(quota_gb=0, duration_days=0)
    assert payload.quota_gb == 0
    assert payload.duration_days == 0


def test_plan_can_be_unlimited_in_time_and_traffic():
    payload = PlanCreate(name="unlimited", quota_gb=0, duration_days=0, max_devices=1, price_minor=0)
    assert payload.quota_gb == 0
    assert payload.duration_days == 0


def test_client_plan_is_optional_and_limits_can_be_direct():
    payload = ClientCreate(user_id=1, quota_gb=0, duration_days=0, single_active=True)
    assert payload.plan_id is None
    assert payload.quota_gb == 0
    assert payload.duration_days == 0
    assert payload.expires_at is None


def test_client_update_accepts_unlimited_limits():
    payload = ClientUpdate(quota_gb=0, duration_days=0, expires_at=None)
    assert payload.quota_gb == 0
    assert payload.duration_days == 0


def test_client_out_allows_planless_and_unlimited():
    payload = ClientOut(
        id=1,
        user_id=1,
        username="plain-user",
        plan_id=None,
        plan_name=None,
        client_id="client",
        node_keys=[],
        enabled=True,
        used_gb=0,
        quota_gb=0,
        expires_at=None,
        created_at=datetime.now(timezone.utc),
    )
    assert payload.plan_id is None
    assert payload.plan_name is None
    assert payload.expires_at is None


def test_explicit_expiry_is_supported():
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    payload = ClientCreate(user_id=1, expires_at=expires)
    assert payload.expires_at == expires
