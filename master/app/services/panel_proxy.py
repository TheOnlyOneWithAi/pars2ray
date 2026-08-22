from __future__ import annotations

import ipaddress
import os
import re
import subprocess
from pathlib import Path

from app.core.config import settings

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
DATA_DIR = Path(os.getenv("PARS2RAY_DATA_DIR", "/opt/pars2ray/data"))
PROXY_CONFIG = DATA_DIR / "panel-nginx.conf"
DOMAIN_FILE = DATA_DIR / "panel-domain.txt"


def validate_domain(domain: str) -> str:
    value = domain.strip().lower().rstrip(".")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not DOMAIN_RE.fullmatch(value):
            raise ValueError("invalid_domain")
        return value
    raise ValueError("domain_required")


def render_config(domain: str, tls: bool, subscription_port: int = 2096) -> str:
    port = settings.panel_http_port
    if subscription_port in {80, 443, port}:
        raise ValueError("invalid_subscription_port")
    if tls:
        return f'''server {{\n    listen 80;\n    server_name {domain};\n    location /.well-known/acme-challenge/ {{ root /var/www/letsencrypt; }}\n    location / {{ return 301 https://$host$request_uri; }}\n}}\n\nserver {{\n    listen 443 ssl http2;\n    server_name {domain};\n    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;\n    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;\n    location / {{ proxy_pass http://127.0.0.1:{port}; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto https; }}\n}}\n\nserver {{\n    listen {subscription_port} ssl http2;\n    server_name {domain};\n    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;\n    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;\n    location / {{ proxy_pass http://127.0.0.1:{port}; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto https; }}\n}}\n'''
    return f'''server {{\n    listen 80;\n    server_name {domain};\n    location /.well-known/acme-challenge/ {{ root /var/www/letsencrypt; }}\n    location / {{ proxy_pass http://127.0.0.1:{port}; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto http; }}\n}}\n\nserver {{\n    listen {subscription_port};\n    server_name {domain};\n    location / {{ proxy_pass http://127.0.0.1:{port}; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto http; }}\n}}\n'''


def _nginx_reload() -> tuple[bool, str]:
    test = subprocess.run(["nginx", "-t"], capture_output=True, text=True, timeout=15, check=False)
    if test.returncode != 0:
        return False, (test.stderr or test.stdout)[-1200:]
    reload_result = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, text=True, timeout=15, check=False)
    if reload_result.returncode != 0:
        return False, (reload_result.stderr or reload_result.stdout)[-1200:]
    return True, "ok"


def apply_proxy(domain: str, tls: bool, email: str | None = None, subscription_port: int = 2096) -> dict:
    domain = validate_domain(domain)
    if subscription_port < 1 or subscription_port > 65535 or subscription_port in {80, 443, settings.panel_http_port}:
        raise ValueError("invalid_subscription_port")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOMAIN_FILE.write_text(domain + "\n", encoding="utf-8")
    if tls:
        if not email or "@" not in email:
            raise ValueError("valid_email_required_for_tls")
        cert_path = Path(f"/etc/letsencrypt/live/{domain}/fullchain.pem/fullchain.pem")
        cert_path = Path(f"/etc/letsencrypt/live/{domain}/fullchain.pem")
        if not cert_path.exists():
            PROXY_CONFIG.write_text(render_config(domain, False, subscription_port), encoding="utf-8")
            ready, detail = _nginx_reload()
            if not ready:
                return {"ok": False, "reason": "nginx_config_invalid", "detail": detail}
            Path("/var/www/letsencrypt").mkdir(parents=True, exist_ok=True)
            cert = subprocess.run(["certbot", "certonly", "--webroot", "-w", "/var/www/letsencrypt", "-d", domain, "--email", email, "--agree-tos", "--non-interactive", "--keep-until-expiring"], capture_output=True, text=True, timeout=120, check=False)
            if cert.returncode != 0:
                return {"ok": False, "reason": "certificate_issuance_failed", "detail": (cert.stderr or cert.stdout)[-1200:]}
    PROXY_CONFIG.write_text(render_config(domain, tls, subscription_port), encoding="utf-8")
    ready, detail = _nginx_reload()
    if not ready:
        return {"ok": False, "reason": "nginx_reload_failed", "detail": detail}
    scheme = "https" if tls else "http"
    return {"ok": True, "domain": domain, "tls": tls, "subscription_port": subscription_port, "url": f"{scheme}://{domain}"}
