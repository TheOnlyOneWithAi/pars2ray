from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.api.deps import require_roles, request_ip
from app.core.security import decrypt_secret
from app.db.base import get_db
from app.models.entities import SystemSetting, User
from app.services.audit import record

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])
ROOT_ROLES = ("SUPER_ADMIN", "ADMIN")
ADMIN_ROLES = ("SUPER_ADMIN", "ADMIN", "OPERATOR")
GEO_DIR = Path(os.getenv("PARS2RAY_GEO_DIR", "/var/lib/pars2ray/geo"))


def _audit(db: Session, user: User, request: Request, action: str, target: str) -> None:
    record(db, user, action, "operations", target, request_ip(request))
    db.commit()


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


@router.get("/backup")
def export_backup(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> Response:
    inspector = inspect(db.bind)
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in sorted(inspector.get_table_names()):
        # Schema identifiers are obtained from SQLAlchemy inspection, never request input.
        rows = db.execute(text(f'SELECT * FROM "{table}"'))  # nosec B608
        tables[table] = [_jsonable(dict(row)) for row in rows.mappings().all()]
    payload = {
        "format": "pars2ray-backup",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
    }
    _audit(db, user, request, "backup.export", "database")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return Response(body, media_type="application/json", headers={"Content-Disposition": 'attachment; filename="pars2ray-backup.json"'})


@router.post("/restore")
async def restore_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="backup_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="invalid_backup") from exc
    if payload.get("format") != "pars2ray-backup" or payload.get("version") != 1 or not isinstance(payload.get("tables"), dict):
        raise HTTPException(status_code=422, detail="unsupported_backup_format")
    inspector = inspect(db.bind)
    allowed = set(inspector.get_table_names())
    restored = 0
    for table, rows in payload["tables"].items():
        if table not in allowed or not isinstance(rows, list):
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        for row in rows:
            if not isinstance(row, dict):
                raise HTTPException(status_code=422, detail=f"invalid_backup_row:{table}")
            values = {k: v for k, v in row.items() if k in columns}
            if not values:
                continue
            names = list(values)
            quoted = ", ".join(f'"{n}"' for n in names)
            placeholders = ", ".join(f":p{i}" for i in range(len(names)))
            db.execute(  # nosec B608
                text(f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'),
                {f"p{i}": values[n] for i, n in enumerate(names)},
            )
            restored += 1
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="backup_restore_failed") from exc
    _audit(db, user, request, "backup.restore", "database")
    return {"ok": True, "rows_restored": restored}


@router.post("/telegram/test")
def telegram_test(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    setting = db.scalar(__import__("sqlalchemy").select(SystemSetting).where(SystemSetting.key == "integration.telegram"))
    if not setting:
        raise HTTPException(status_code=404, detail="telegram_not_configured")
    try:
        cfg = json.loads(decrypt_secret(setting.value_enc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="invalid_telegram_settings") from exc
    token = str(cfg.get("bot_token") or "").strip()
    chat_id = str(payload.get("chat_id") or (cfg.get("chat_ids") or [""])[0]).strip()
    message = str(payload.get("message") or "Pars2Ray Telegram test").strip()
    if not token or not chat_id or not message or len(message) > 4096:
        raise HTTPException(status_code=422, detail="invalid_telegram_test")
    token_path = urllib.parse.quote(token, safe="")
    url = f"https://api.telegram.org/bot{token_path}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
    try:
        request_obj = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(request_obj, timeout=10) as response:  # nosec B310
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="telegram_unreachable") from exc
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail="telegram_rejected")
    _audit(db, user, request, "telegram.test", chat_id)
    return {"ok": True}


@router.get("/fail2ban/status")
def fail2ban_status(user: User = Depends(require_roles(*ADMIN_ROLES))) -> dict[str, Any]:
    try:
        installed = subprocess.run(["sh", "-c", "command -v fail2ban-client >/dev/null 2>&1"], capture_output=True, timeout=3).returncode == 0
        if not installed:
            return {"installed": False, "running": False, "jails": []}
        result = subprocess.run(["fail2ban-client", "status"], capture_output=True, text=True, timeout=5)
        return {"installed": True, "running": result.returncode == 0, "raw": result.stdout.strip(), "error": result.stderr.strip()}
    except (OSError, subprocess.SubprocessError):
        return {"installed": False, "running": False, "jails": []}


@router.post("/geo/update")
def update_geo(payload: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles(*ROOT_ROLES))) -> dict[str, Any]:
    geoip_url = str(payload.get("geoip_url") or "").strip()
    geosite_url = str(payload.get("geosite_url") or "").strip()
    urls = {"geoip": geoip_url, "geosite": geosite_url}
    if not any(urls.values()):
        raise HTTPException(status_code=422, detail="geo_url_required")
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    downloaded: dict[str, str] = {}
    for name, url in urls.items():
        if not url:
            continue
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=422, detail=f"invalid_{name}_url")
        target = GEO_DIR / f"{name}.dat"
        tmp = GEO_DIR / f".{name}.dat.tmp"
        try:
            with urllib.request.urlopen(url, timeout=30) as response, tmp.open("wb") as out:  # nosec B310
                size = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > 100 * 1024 * 1024:
                        raise ValueError("geo_file_too_large")
                    out.write(chunk)
            if size < 16:
                raise ValueError("geo_file_too_small")
            os.replace(tmp, target)
            downloaded[name] = str(target)
        except Exception as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise HTTPException(status_code=502, detail=f"geo_update_failed:{name}") from exc
    _audit(db, user, request, "geo.update", "geoip/geosite")
    return {"ok": True, "files": downloaded}
