from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.domain.users.models import User
from app.domain.economy.rate_service import calculate_user_rate


MAX_OFFLINE_SECONDS = 12 * 60 * 60  # 12 hours


@dataclass
class OfflineIncomeResult:
    earned: int
    seconds_used: int
    rate_per_sec: float


async def apply_offline_income(session, user: User) -> OfflineIncomeResult:
    """
    درآمد آفلاین را اعمال می‌کند.

    منطق:
    - از last_claim_at تا الان را حساب می‌کنیم
    - سقف 12 ساعت
    - نرخ تولید نهایی را از rate_service می‌گیریم (Cats + Items)
    - earned = floor(rate * seconds)
    - earned به meow_points اضافه می‌شود
    - last_claim_at آپدیت می‌شود
    """

    now = datetime.now(timezone.utc)

    # اولین بار: فقط last_claim_at را تنظیم کن
    if user.last_claim_at is None:
        user.last_claim_at = now
        await session.commit()
        return OfflineIncomeResult(earned=0, seconds_used=0, rate_per_sec=0.0)

    seconds = int((now - user.last_claim_at).total_seconds())
    if seconds <= 0:
        return OfflineIncomeResult(earned=0, seconds_used=0, rate_per_sec=0.0)

    # سقف 12 ساعت
    seconds_used = min(seconds, MAX_OFFLINE_SECONDS)

    # نرخ نهایی تولید (با آیتم‌ها)
    breakdown = await calculate_user_rate(session, user.telegram_id)
    rate_per_sec = breakdown.final_per_sec

    earned = int(rate_per_sec * seconds_used)

    # اگر نرخ صفر است یا درآمد صفر
    if earned <= 0:
        user.last_claim_at = now
        await session.commit()
        return OfflineIncomeResult(earned=0, seconds_used=seconds_used, rate_per_sec=rate_per_sec)

    # اعمال درآمد
    user.meow_points += earned
    user.last_claim_at = now
    await session.commit()

    return OfflineIncomeResult(earned=earned, seconds_used=seconds_used, rate_per_sec=rate_per_sec)
