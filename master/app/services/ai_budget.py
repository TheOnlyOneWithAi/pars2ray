from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.entities import Decision


def _cost(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    billable_input = max(0, input_tokens - cached_tokens)
    return (
        billable_input / 1_000_000 * settings.ai_input_cost_per_million_usd
        + cached_tokens / 1_000_000 * settings.ai_cached_input_cost_per_million_usd
        + output_tokens / 1_000_000 * settings.ai_output_cost_per_million_usd
    )


def _spent_since(db, start: datetime) -> float:
    rows = db.execute(
        select(
            func.coalesce(func.sum(Decision.input_tokens), 0),
            func.coalesce(func.sum(Decision.cached_tokens), 0),
            func.coalesce(func.sum(Decision.output_tokens), 0),
        ).where(Decision.ai_called.is_(True), Decision.created_at >= start)
    ).one()
    return _cost(int(rows[0]), int(rows[1]), int(rows[2]))


def estimate_call_cost(input_chars: int) -> float:
    # Conservative preflight estimate: UTF-8 JSON averages roughly four chars/token.
    estimated_input = max(1, input_chars // 4)
    return _cost(estimated_input, 0, settings.ai_max_output_tokens)


def budget_status() -> dict:
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as db:
        daily = _spent_since(db, now - timedelta(days=1))
        monthly = _spent_since(db, month_start)
    return {
        "daily_budget_usd": settings.ai_budget_daily_usd,
        "monthly_budget_usd": settings.ai_budget_monthly_usd,
        "daily_spent_usd": round(daily, 6),
        "monthly_spent_usd": round(monthly, 6),
        "daily_remaining_usd": round(max(0.0, settings.ai_budget_daily_usd - daily), 6),
        "monthly_remaining_usd": round(max(0.0, settings.ai_budget_monthly_usd - monthly), 6),
    }


def can_call(input_chars: int) -> tuple[bool, str]:
    if settings.ai_budget_daily_usd <= 0 or settings.ai_budget_monthly_usd <= 0:
        return False, "AI budget is disabled."
    status = budget_status()
    estimated = estimate_call_cost(input_chars) / max(settings.ai_budget_safety_margin, 0.01)
    if estimated > status["daily_remaining_usd"]:
        return False, "Daily AI budget exhausted or too close to its safety limit."
    if estimated > status["monthly_remaining_usd"]:
        return False, "Monthly AI budget exhausted or too close to its safety limit."
    return True, "budget_ok"
