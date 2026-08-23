from app.api.advanced_control import OUTBOUND_PROTOCOLS, _validate


def test_outbound_protocol_inventory_is_real():
    assert {"freedom", "blackhole", "dns", "http", "socks", "vmess", "vless", "trojan", "shadowsocks", "wireguard", "loopback"}.issubset(OUTBOUND_PROTOCOLS)


def test_outbound_validation_requires_unique_tags():
    items = [{"id": "a", "tag": "direct", "protocol": "freedom"}, {"id": "b", "tag": "direct", "protocol": "blackhole"}]
    try:
        _validate("outbounds", items)
    except Exception as exc:
        assert getattr(exc, "detail", "") == "duplicate_outbound_tag"
    else:
        raise AssertionError("duplicate outbound tags must be rejected")


def test_routing_validation_accepts_rules():
    value = _validate("routing", {"domainStrategy": "AsIs", "rules": [{"id": "r1", "domain": ["geosite:ir"], "outboundTag": "direct"}]})
    assert value["rules"][0]["outboundTag"] == "direct"
