from app.services.ai_autopilot import LEVELS
from app.services.candidate_engine import generate
from app.services.config_builder import build_config


def test_ai_levels_are_monotonic_and_explicit():
    assert LEVELS == {"off": 0, "advisor": 1, "inbounds": 2, "nodes": 3, "autonomous": 4}


def test_candidate_generation_includes_singbox_hysteria2():
    rows = generate(["IR1"], 100, allow_experimental=True)
    assert any(row["core"] == "sing-box" and row["protocol"] == "hysteria2" for row in rows)


def test_advanced_xray_inbound_builder_uses_raw_settings():
    config = build_config({"name": "wg", "core": "xray", "protocol": "wireguard", "transport": "tcp", "config": {"port": 51820, "settings": {"secretKey": "test"}}}, [])
    assert config["inbounds"][0]["protocol"] == "wireguard"
    assert config["inbounds"][0]["settings"] == {"secretKey": "test"}
