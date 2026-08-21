from app.services.config_builder import build_config


def test_xray_vless_tls_grpc_config():
    config = build_config({"name": "secure", "core": "xray", "protocol": "vless", "transport": "grpc", "config": {"port": 443, "tls": True, "server_name": "panel.example.com", "service_name": "ray"}}, [{"id": "11111111-1111-4111-8111-111111111111"}])
    inbound = config["inbounds"][0]
    assert inbound["protocol"] == "vless"
    assert inbound["settings"]["decryption"] == "none"
    assert inbound["streamSettings"]["network"] == "grpc"
    assert inbound["streamSettings"]["security"] == "tls"


def test_xray_vmess_websocket_config():
    config = build_config({"name": "vmess", "core": "xray", "protocol": "vmess", "transport": "websocket", "config": {"path": "/ray"}}, [{"id": "11111111-1111-4111-8111-111111111111"}])
    inbound = config["inbounds"][0]
    assert inbound["protocol"] == "vmess"
    assert inbound["settings"]["clients"][0]["id"].startswith("1111")
    assert inbound["streamSettings"]["network"] == "ws"


def test_xray_trojan_config():
    config = build_config({"name": "trojan", "core": "xray", "protocol": "trojan", "transport": "tcp", "config": {}}, [{"id": "secret"}])
    assert config["inbounds"][0]["settings"]["clients"][0]["password"] == "secret"


def test_xray_shadowsocks_config():
    config = build_config({"name": "ss", "core": "xray", "protocol": "shadowsocks", "transport": "tcp", "config": {"method": "aes-128-gcm"}}, [{"id": "secret"}])
    assert config["inbounds"][0]["settings"]["method"] == "aes-128-gcm"
    assert config["inbounds"][0]["settings"]["password"] == "secret"


def test_singbox_hysteria2_config():
    config = build_config({"name": "hy2", "core": "sing-box", "protocol": "hysteria2", "transport": "tcp", "config": {}}, [{"id": "secret"}])
    assert config["inbounds"][0]["type"] == "hysteria2"
    assert config["inbounds"][0]["users"][0]["password"] == "secret"
