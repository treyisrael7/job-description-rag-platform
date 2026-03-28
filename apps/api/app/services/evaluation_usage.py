"""Monthly evaluation quotas per user plan (cost and abuse control)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

_PLAN_ALIASES = {
    "free": "free",
    "pro": "pro",
    "enterprise": "enterprise",
    "business": "enterprise",
}


def _normalize_plan(raw: str | None) -> str:
    s = (raw or "free").strip().lower()
    return _PLAN_ALIASES.get(s, "free")


def evaluation_limit_for_plan(plan: str | None) -> int:
    """Max evaluations per calendar month (UTC) for this plan."""
    p = _normalize_plan(plan)
    if p == "pro":
        return max(0, settings.plan_limit_pro)
    if p == "enterprise":
        return max(0, settings.plan_limit_enterprise)
    return max(0, settings.plan_limit_free)


def _current_usage_month_utc() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def consume_evaluation_quota(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> tuple[int, int, str]:
    """
    Atomically increment this month's evaluation count if under the plan limit.

    Uses a row lock on ``users``. Call before the expensive LLM evaluation; rolls back
    with the request transaction if evaluation fails.

    Returns ``(evaluations_used_this_month_after, limit, plan)``.
    """
    r = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = r.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    plan = _normalize_plan(getattr(user, "plan", None))
    limit = evaluation_limit_for_plan(plan)

    if settings.demo_auth_active and user_id == settings.demo_user_id:
        limit = max(0, settings.demo_monthly_evaluation_limit)

    ym = _current_usage_month_utc()
    stored = getattr(user, "evaluation_usage_month", None)
    used = int(getattr(user, "evaluations_this_month", 0) or 0)

    if stored != ym:
        used = 0
        user.evaluation_usage_month = ym

    if limit > 0 and used >= limit:
        logger.info(
            "evaluation quota exceeded user_id=%s plan=%s used=%s limit=%s",
            user_id,
            plan,
            used,
            limit,
        )
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly evaluation limit reached ({limit}) for your plan ({plan}). "
                "Upgrade your plan or try again next month."
            ),
        )

    user.evaluations_this_month = used + 1
    user.evaluation_usage_month = ym

    await db.flush()
    return (user.evaluations_this_month, limit, plan)
