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


EDITABLE = {
    "optimizer.enabled", "optimizer.min_score_change", "national_mode.enabled",
    "ai.enabled", "ai.model", "ai.api_key", "ai.level", "ai.autonomous",
    "ai.probe_country", "ai.max_nodes", "ai.max_candidates",
}


def _validate(key: str, value: str) -> None:
    if key in {"ai.enabled", "ai.autonomous", "optimizer.enabled", "national_mode.enabled"} and value.lower() not in {"true", "false"}:
        raise HTTPException(status_code=422, detail=f"{key}_must_be_boolean")
    if key == "ai.model" and not value:
        raise HTTPException(status_code=422, detail="invalid_ai_model")
    if key == "ai.api_key" and len(value) < 20:
        raise HTTPException(status_code=422, detail="invalid_openai_api_key")
    if key == "ai.level":
        try:
            if not 0 <= int(value) <= 4 and value.lower() not in {"off", "advisor", "inbounds", "nodes", "autonomous"}:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="ai.level_must_be_0_to_4") from exc
    if key == "ai.probe_country" and (len(value) != 2 or not value.isalpha()):
        raise HTTPException(status_code=422, detail="ai.probe_country_must_be_iso2")
    if key in {"ai.max_nodes", "ai.max_candidates"}:
        try:
            number = int(value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{key}_must_be_integer") from exc
        if not 1 <= number <= 100:
            raise HTTPException(status_code=422, detail=f"{key}_out_of_range")


@router.get("/system/settings", tags=["system"])
def list_settings(db: Session = Depends(get_db), user: User = admin()) -> list[dict]:
    rows = db.scalars(select(SystemSetting).order_by(SystemSetting.key)).all()
    return [{"key": row.key, "is_secret": row.is_secret, "updated_at": row.updated_at} for row in rows]


@router.put("/system/settings/{key}", tags=["system"])
def update_setting(key: str, payload: SystemSettingUpdate, request: Request, db: Session = Depends(get_db), user: User = admin()) -> dict:
    if key not in EDITABLE:
        raise HTTPException(status_code=422, detail="setting_not_editable")
    value = payload.value.strip()
    _validate(key, value)
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
    keys = ["ai.enabled", "ai.model", "ai.api_key", "ai.level", "ai.autonomous", "ai.probe_country", "ai.max_nodes", "ai.max_candidates"]
    rows = {row.key: row for row in db.scalars(select(SystemSetting).where(SystemSetting.key.in_(keys))).all()}
    def value(key: str, default: str) -> str:
        return decrypt_secret(rows[key].value_enc) if key in rows else default
    enabled = value("ai.enabled", "false").lower() == "true"
    configured = "ai.api_key" in rows
    return {
        "enabled": bool(enabled and configured),
        "configured": configured,
        "model": value("ai.model", "gpt-5-mini"),
        "level": value("ai.level", "0"),
        "autonomous": value("ai.autonomous", "false").lower() == "true",
        "probe_country": value("ai.probe_country", "IR").upper(),
        "max_nodes": int(value("ai.max_nodes", "50")),
        "max_candidates": int(value("ai.max_candidates", "12")),
    }
