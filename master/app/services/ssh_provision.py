from __future__ import annotations

import io
import json
import shlex
from dataclasses import dataclass
from pathlib import Path

import paramiko

from app.core.security import decrypt_secret


@dataclass(frozen=True)
class SSHConfig:
    host: str
    port: int
    username: str
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None


def decode_config(value: str) -> SSHConfig:
    raw = json.loads(decrypt_secret(value))
    return SSHConfig(host=str(raw["host"]).strip(), port=int(raw.get("port", 22)), username=str(raw["username"]).strip(), password=raw.get("password") or None, private_key=raw.get("private_key") or None, passphrase=raw.get("passphrase") or None)


def _client(config: SSHConfig) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    known_hosts.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pkey = None
    if config.private_key:
        key_stream = io.StringIO(config.private_key)
        for key_type in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey):
            try:
                key_stream.seek(0)
                pkey = key_type.from_private_key(key_stream, password=config.passphrase)
                break
            except (paramiko.SSHException, ValueError):
                continue
        if pkey is None:
            raise ValueError("invalid_private_key")
    client.connect(config.host, port=config.port, username=config.username, password=config.password, pkey=pkey, timeout=15, banner_timeout=15, auth_timeout=15, look_for_keys=False, allow_agent=False)
    client.save_host_keys(str(known_hosts))
    return client


INSTALL_SCRIPT = r'''set -eu
export DEBIAN_FRONTEND=noninteractive
command -v python3 >/dev/null 2>&1 || { apt-get update -o Acquire::Retries=2 -o Acquire::ForceIPv4=true; apt-get install -y python3; }
command -v git >/dev/null 2>&1 || { apt-get update -o Acquire::Retries=2 -o Acquire::ForceIPv4=true; apt-get install -y git; }
python3 -m venv /opt/pars2ray-agent/.venv 2>/dev/null || { apt-get update -o Acquire::Retries=2 -o Acquire::ForceIPv4=true; apt-get install -y python3-venv; python3 -m venv /opt/pars2ray-agent/.venv; }
if [ ! -d /opt/pars2ray-agent/.git ]; then
  rm -rf /opt/pars2ray-agent
  git clone --depth 1 https://github.com/TheOnlyOneWithAi/pars2ray.git /opt/pars2ray-agent
else
  git -C /opt/pars2ray-agent fetch --depth 1 origin main
  git -C /opt/pars2ray-agent reset --hard origin/main
fi
/opt/pars2ray-agent/.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r /opt/pars2ray-agent/agent/requirements.txt
install -d -m 0750 /var/lib/pars2ray-agent
cat >/etc/systemd/system/pars2ray-agent.service <<'UNIT'
[Unit]
Description=Pars2Ray Node Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/pars2ray-agent/agent
Environment=NODE_KEY=__NODE_KEY__
Environment=COUNTRY=__COUNTRY__
Environment=AGENT_TOKEN=__AGENT_TOKEN__
Environment=AGENT_VERSION=2.3.0
Environment=AGENT_STATE_DIR=/var/lib/pars2ray-agent
ExecStart=/opt/pars2ray-agent/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9100 --proxy-headers --timeout-keep-alive 15
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ReadWritePaths=/var/lib/pars2ray-agent /etc/xray /etc/sing-box /usr/local/etc/xray /usr/local/etc/sing-box

[Install]
WantedBy=multi-user.target
UNIT
sed -i "s|__NODE_KEY__|NODE_KEY_VALUE|g; s|__COUNTRY__|COUNTRY_VALUE|g; s|__AGENT_TOKEN__|AGENT_TOKEN_VALUE|g" /etc/systemd/system/pars2ray-agent.service
systemctl daemon-reload
systemctl enable --now pars2ray-agent
systemctl is-active --quiet pars2ray-agent
curl -fsS --max-time 8 http://127.0.0.1:9100/health >/dev/null
'''


def provision(config: SSHConfig, node_key: str, country: str, agent_token: str) -> None:
    client = _client(config)
    try:
        script = INSTALL_SCRIPT.replace("NODE_KEY_VALUE", shlex.quote(node_key)).replace("COUNTRY_VALUE", shlex.quote(country)).replace("AGENT_TOKEN_VALUE", shlex.quote(agent_token))
        command = "printf '%s\\n' %s | bash" % (shlex.quote(script), "")
        _, stdout, stderr = client.exec_command(command, timeout=180)
        code = stdout.channel.recv_exit_status()
        if code != 0:
            detail = stderr.read().decode("utf-8", "replace")[-2000:]
            raise RuntimeError(f"node_agent_install_failed:{detail or code}")
    finally:
        client.close()


def test(config: SSHConfig) -> dict:
    client = _client(config)
    try:
        _, stdout, stderr = client.exec_command("uname -srm && id -un", timeout=15)
        code = stdout.channel.recv_exit_status()
        if code != 0:
            raise RuntimeError(stderr.read().decode("utf-8", "replace")[-1000:] or "ssh_command_failed")
        return {"ok": True, "output": stdout.read().decode("utf-8", "replace").strip()}
    finally:
        client.close()
