from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path

from app.core.config import settings

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
DATA_DIR = Path(settings.data_dir)
PROXY_CONFIG = DATA_DIR / "panel-nginx.conf"


def validate_domain(domain: str) -> str:
    value = domain.strip().lower().rstrip(".")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not DOMAIN_RE.fullmatch(value):
            raise ValueError("invalid_domain")
        return value
    raise ValueError("domain_required")


def render_config(domain: str, tls: bool) -> str:
    if tls:
        return f'''server {{\n    listen 80;\n    server_name {domain};\n    location /.well-known/acme-challenge/ {{ root /var/www/letsencrypt; }}\n    location / {{ return 301 https://$host$request_uri; }}\n}}\n\nserver {{\n    listen 443 ssl http2;\n    server_name {domain};\n    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;\n    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;\n    location / {{ proxy_pass http://127.0.0.1:{settings.panel_port}; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto https; }}\n}}\n'''
    return f'''server {{\n    listen 80;\n    server_name {domain};\n    location / {{ proxy_pass http://127.0.0.1:{settings.panel_port}; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto http; }}\n}}\n'''


def apply_proxy(domain: str, tls: bool, email: str | None = None) -> dict:
    domain = validate_domain(domain)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if tls:
        if not email or "@" not in email:
            raise ValueError("valid_email_required_for_tls")
        if not Path(f"/etc/letsencrypt/live/{domain}/fullchain.pem").exists():
            Path("/var/www/letsencrypt").mkdir(parents=True, exist_ok=True)
            cert = subprocess.run(["certbot", "certonly", "--webroot", "-w", "/var/www/letsencrypt", "-d", domain, "--email", email, "--agree-tos", "--non-interactive", "--keep-until-expiring"], capture_output=True, text=True, timeout=120, check=False)
            if cert.returncode != 0:
                return {"ok": False, "reason": "certificate_issuance_failed", "detail": (cert.stderr or cert.stdout)[-1200:]}
    PROXY_CONFIG.write_text(render_config(domain, tls), encoding="utf-8")
    test = subprocess.run(["nginx", "-t"], capture_output=True, text=True, timeout=15, check=False)
    if test.returncode != 0:
        return {"ok": False, "reason": "nginx_config_invalid", "detail": (test.stderr or test.stdout)[-1200:]}
    reload_result = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, text=True, timeout=15, check=False)
    if reload_result.returncode != 0:
        return {"ok": False, "reason": "nginx_reload_failed", "detail": (reload_result.stderr or reload_result.stdout)[-1200:]}
    return {"ok": True, "domain": domain, "tls": tls, "url": f"https://{domain}" if tls else f"http://{domain}"}
