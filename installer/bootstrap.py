from __future__ import annotations

import getpass
import io
import os
import re
import secrets
import shlex
import tarfile
import time
from pathlib import Path

import httpx
import paramiko
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ENV = dict(dotenv_values(ENV_PATH))
NODE_KEY_RE = re.compile(r"^[A-Z]{2}\d+$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")


def val(name, default=""):
    return (ENV.get(name) or default).strip()


def required(name):
    v = val(name)
    if not v and os.isatty(0):
        prompt = f"{name}: "
        v = (getpass.getpass(prompt) if name.endswith(("_PASS", "_PASSWORD")) else input(prompt)).strip()
        if v:
            set_key(str(ENV_PATH), name, v)
            ENV[name] = v
    if not v:
        raise SystemExit(f"Missing required {name}; provide it in .env or an interactive terminal")
    return v


def save_env(name, value):
    set_key(str(ENV_PATH), name, value)
    ENV[name] = value


def prompt_node_credentials(nodes):
    if not os.isatty(0):
        return
    for n in nodes:
        if not n["password"]:
            n["password"] = getpass.getpass(f"{n['node_key']} SSH password: ").strip()
            if n["password"]:
                save_env(f"{n['node_key']}_PASS", n["password"])
        if not n["user"] or n["user"] == "root":
            entered = input(f"{n['node_key']} SSH user [root]: ").strip() or "root"
            n["user"] = entered
            save_env(f"{n['node_key']}_USER", entered)


def _prompt_int(label, default, minimum, maximum):
    while True:
        raw = input(f"{label} [{default}]: ").strip() or str(default)
        try:
            value = int(raw)
        except ValueError:
            print(f"Please enter a number between {minimum} and {maximum}.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"Please enter a number between {minimum} and {maximum}.")


def _prompt_required(label, default=""):
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip() or default
        if value:
            return value
        print("This value is required.")


def prompt_nodes_interactively():
    """Ask for the node count, then collect each node in a predictable order."""
    if not os.isatty(0):
        return discover_nodes()

    print("\n=== Pars2Ray Node Setup ===")
    count = _prompt_int("How many nodes do you have?", 1, 0, 100)
    nodes = []
    used_keys = set()

    for index in range(1, count + 1):
        print(f"\n--- Node {index}/{count} ---")
        while True:
            country = _prompt_required("Country code (2 letters)").upper()
            if COUNTRY_RE.fullmatch(country):
                break
            print("Country code must contain exactly two letters, for example DE or NL.")

        default_key = f"{country}{index}"
        while True:
            node_key = _prompt_required("Node key", default_key).upper()
            if NODE_KEY_RE.fullmatch(node_key) and node_key not in used_keys:
                break
            print("Node key must look like DE1, NL2, etc. and must be unique.")

        ip = _prompt_required("SSH host / IP")
        user = _prompt_required("SSH user", "root")
        password = getpass.getpass("SSH password: ").strip()
        while not password:
            print("SSH password is required for the installer.")
            password = getpass.getpass("SSH password: ").strip()
        port = _prompt_int("SSH port", 22, 1, 65535)

        node = {
            "node_key": node_key,
            "country": country,
            "ip": ip,
            "user": user,
            "password": password,
            "port": port,
        }
        nodes.append(node)
        used_keys.add(node_key)

        save_env(f"{node_key}_IP", ip)
        save_env(f"{node_key}_USER", user)
        save_env(f"{node_key}_PASS", password)
        save_env(f"{node_key}_PORT", str(port))

    print(f"\nCollected {len(nodes)} node(s).")
    for node in nodes:
        print(f"  - {node['node_key']} ({node['country']}) -> {node['ip']}:{node['port']}")
    return nodes


def ssh(ip, user, password, port):
    c = paramiko.SSHClient()
    known_hosts = Path(val("PARS2RAY_KNOWN_HOSTS", "~/.ssh/known_hosts")).expanduser()
    if known_hosts.exists():
        c.load_host_keys(str(known_hosts))
    c.set_missing_host_key_policy(paramiko.RejectPolicy())
    c.connect(ip, port=port, username=user, password=password, timeout=18, banner_timeout=18, auth_timeout=18)
    return c


def run(c, cmd):
    # Commands are built from fixed installer strings; caller-controlled values are shell-quoted.
    _, out, err = c.exec_command(cmd, get_pty=True)  # nosec B601
    code = out.channel.recv_exit_status()
    _ = out.read()
    __ = err.read()
    if code != 0:
        raise RuntimeError(f"remote command failed ({code})")


def upload_tree(c, local, remote):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w:gz") as tf:
        tf.add(local, arcname=local.name)
    b.seek(0)
    s = c.open_sftp()
    try:
        remote_home = s.normalize(".")
        if not remote_home or not remote_home.startswith("/"):
            raise RuntimeError("could not determine remote home directory")
        tmp = f"{remote_home}/.pars2ray-upload-{secrets.token_hex(16)}.tgz"
        with s.file(tmp, "wb") as f:
            f.write(b.read())
    finally:
        s.close()

    command = (
        f"trap 'rm -f -- {shlex.quote(tmp)}' EXIT; "
        f"mkdir -p {shlex.quote(remote)} && "
        f"tar xzf {shlex.quote(tmp)} -C {shlex.quote(remote)} --strip-components=1"
    )
    run(c, command)


def upload_file(c, local, remote, mode=0o600):
    s = c.open_sftp()
    try:
        s.put(str(local), remote)
        s.chmod(remote, mode)
    finally:
        s.close()


def _node_port(prefix):
    raw = val(prefix + "_PORT", "22")
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{prefix}_PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise SystemExit(f"{prefix}_PORT must be an integer between 1 and 65535")
    return port


def discover_nodes():
    pat = re.compile(r"^([A-Z]{2})(\d+)_IP$")
    out = []
    for key, ip in ENV.items():
        m = pat.match(key)
        if not m or not (ip or "").strip():
            continue
        prefix = m.group(1) + m.group(2)
        out.append(
            {
                "node_key": prefix,
                "country": m.group(1),
                "ip": ip.strip(),
                "user": val(prefix + "_USER", "root"),
                "password": val(prefix + "_PASS"),
                "port": _node_port(prefix),
            }
        )
    return sorted(out, key=lambda x: x["node_key"])


def install_master():
    ip = required("PANEL_IP")
    configured_hosts = [host.strip() for host in val("TRUSTED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
    if ip not in configured_hosts:
        configured_hosts.append(ip)
        save_env("TRUSTED_HOSTS", ",".join(configured_hosts))
    c = ssh(ip, required("PANEL_USER"), required("PANEL_PASS"), int(val("PANEL_PORT", "22")))
    run(c, "command -v docker >/dev/null 2>&1 || (apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-plugin)")
    run(c, "systemctl enable --now docker")
    upload_tree(c, ROOT, "/opt/pars2ray")
    upload_file(c, ENV_PATH, "/opt/pars2ray/.env")
    run(c, "cd /opt/pars2ray/deploy && docker compose --env-file ../.env up -d --build")
    c.close()
    print(f"[MASTER] installed at {ip}")
    return ip


def install_node(n, master_ip):
    token = secrets.token_urlsafe(40)
    ai_node = val("AI_NODE").upper()
    is_ai = n["node_key"].upper() == ai_node and bool(val("OPENAI_API_KEY"))
    c = ssh(n["ip"], n["user"], n["password"], n["port"])
    run(c, "apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv")
    upload_tree(c, ROOT / "agent", "/opt/pars2ray-agent")
    env = (
        f"NODE_KEY={n['node_key']}\n"
        f"COUNTRY={n['country']}\n"
        f"AGENT_TOKEN={token}\n"
        f"AI_RELAY_ENABLED={'true' if is_ai else 'false'}\n"
        f"OPENAI_API_KEY={val('OPENAI_API_KEY') if is_ai else ''}\n"
        f"OPENAI_BASE_URL={val('OPENAI_BASE_URL', 'https://api.openai.com/v1')}\n"
    )
    s = c.open_sftp()
    try:
        with s.file("/opt/pars2ray-agent/.env", "w") as f:
            f.write(env)
        s.chmod("/opt/pars2ray-agent/.env", 0o600)
    finally:
        s.close()
    service = """[Unit]\nDescription=Pars2Ray Node Agent\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory=/opt/pars2ray-agent\nEnvironmentFile=/opt/pars2ray-agent/.env\nExecStart=/opt/pars2ray-agent/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9100\nRestart=always\nRestartSec=3\nNoNewPrivileges=true\n\n[Install]\nWantedBy=multi-user.target\n"""
    s = c.open_sftp()
    try:
        with s.file("/etc/systemd/system/pars2ray-agent.service", "w") as f:
            f.write(service)
    finally:
        s.close()
    run(c, "cd /opt/pars2ray-agent && python3 -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt && systemctl daemon-reload && systemctl enable --now pars2ray-agent")
    run(c, f"command -v ufw >/dev/null 2>&1 && ufw status | grep -q 'Status: active' && ufw allow from {shlex.quote(master_ip)} to any port 9100 proto tcp || true")
    c.close()
    print(f"[{n['node_key']}] agent installed")
    return token, is_ai


def register(master_ip, n, token):
    url = f"http://{master_ip}:{val('PANEL_HTTP_PORT', '8000')}/api/v1/nodes/register"
    body = {"node_key": n["node_key"], "country": n["country"], "endpoint": f"http://{n['ip']}:9100", "agent_token": token}
    for attempt in range(12):
        try:
            r = httpx.post(url, headers={"X-Master-Secret": required("MASTER_SECRET")}, json=body, timeout=8)
            r.raise_for_status()
            return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise RuntimeError(f"node registration rejected with HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError:
            pass
        if attempt < 11:
            time.sleep(3)
    raise RuntimeError(f"could not register {n['node_key']} with master")


def configure_relay(master_ip, n, token):
    relay = f"http://{n['ip']}:9100/ai/responses"
    save_env("AI_RELAY_URL", relay)
    save_env("AI_RELAY_TOKEN", token)
    c = ssh(master_ip, required("PANEL_USER"), required("PANEL_PASS"), int(val("PANEL_PORT", "22")))
    upload_file(c, ENV_PATH, "/opt/pars2ray/.env")
    run(c, "cd /opt/pars2ray/deploy && docker compose --env-file ../.env up -d --build master")
    c.close()
    print(f"[AI] relay configured on {n['node_key']}")


def main():
    if not ENV_PATH.exists():
        raise SystemExit("Copy .env.example to .env and fill it first.")

    nodes = prompt_nodes_interactively() if os.isatty(0) else discover_nodes()
    if os.isatty(0) and not nodes:
        print("No nodes selected. The Master will be installed without node agents.")

    master = install_master()
    relay = None
    failed_nodes = []
    print(f"[DISCOVERY] {len(nodes)} node(s)")
    for n in nodes:
        try:
            token, is_ai = install_node(n, master)
            register(master, n, token)
            if is_ai:
                relay = (n, token)
        except Exception as e:
            failed_nodes.append(n["node_key"])
            print(f"[{n['node_key']}] FAILED: {type(e).__name__}: {e}")

    if relay:
        configure_relay(master, *relay)

    print(f"UI: http://{master}:{val('PANEL_HTTP_PORT', '8000')}/")
    print(f"OpenAPI: http://{master}:{val('PANEL_HTTP_PORT', '8000')}/openapi.json")
    if failed_nodes:
        raise SystemExit(f"Node installation failed for: {', '.join(failed_nodes)}")


if __name__ == "__main__":
    main()
