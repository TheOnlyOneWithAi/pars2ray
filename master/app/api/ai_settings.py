from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import decrypt_secret, encrypt_secret
from app.db.base import get_db
from app.models.entities import SystemSetting, User
from app.schemas import SystemSettingUpdate

router = APIRouter(prefix="/api/v1")


def admin():
    return Depends(require_roles("SUPER_ADMIN"))


@router.get("/system/settings", tags=["system"])
def list_settings(db: Session = Depends(get_db), user: User = admin()) -> list[dict]:
    rows = db.scalars(select(SystemSetting).order_by(SystemSetting.key)).all()
    return [{"key": row.key, "is_secret": row.is_secret, "updated_at": row.updated_at} for row in rows]


@router.put("/system/settings/{key}", tags=["system"])
def update_setting(key: str, payload: SystemSettingUpdate, request: Request, db: Session = Depends(get_db), user: User = admin()) -> dict:
    editable = {"optimizer.enabled", "optimizer.min_score_change", "national_mode.enabled", "ai.enabled", "ai.model", "ai.api_key"}
    if key not in editable:
        raise HTTPException(status_code=422, detail="setting_not_editable")
    value = payload.value.strip()
    if key == "ai.enabled" and value.lower() not in {"true", "false"}:
        raise HTTPException(status_code=422, detail="ai.enabled_must_be_boolean")
    if key == "ai.model" and not value:
        raise HTTPException(status_code=422, detail="invalid_ai_model")
    if key == "ai.api_key" and len(value) < 20:
        raise HTTPException(status_code=422, detail="invalid_openai_api_key")
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not row:
        row = SystemSetting(key=key, value_enc=encrypt_secret(value), is_secret=(key == "ai.api_key"))
        db.add(row)
    else:
        row.value_enc = encrypt_secret(value)
        row.is_secret = key == "ai.api_key"
    db.commit()
    return {"ok": True, "key": key, "is_secret": row.is_secret}


@router.get("/system/ai-status", tags=["system"])
def ai_status(db: Session = Depends(get_db), user: User = admin()) -> dict:
    rows = {row.key: row for row in db.scalars(select(SystemSetting).where(SystemSetting.key.in_(["ai.enabled", "ai.model", "ai.api_key"]))).all()}
    enabled = decrypt_secret(rows["ai.enabled"].value_enc).lower() == "true" if "ai.enabled" in rows else False
    model = decrypt_secret(rows["ai.model"].value_enc) if "ai.model" in rows else "gpt-5-mini"
    configured = "ai.api_key" in rows
    return {"enabled": bool(enabled and configured), "configured": configured, "model": model}
