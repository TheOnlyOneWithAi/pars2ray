from app.main import _is_legacy_username_link


def test_short_link_values_are_rejected_as_username_compatibility_paths():
    assert _is_legacy_username_link("/link/alice") is True
    assert _is_legacy_username_link("/link/alice/raw") is True


def test_long_subscription_tokens_are_not_classified_as_usernames():
    token = "a" * 64
    assert _is_legacy_username_link(f"/link/{token}") is False


def test_non_link_paths_are_not_classified():
    assert _is_legacy_username_link("/s/token") is False
    assert _is_legacy_username_link("/link/") is False
