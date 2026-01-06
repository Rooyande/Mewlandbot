from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.domain.users.models import User
from app.domain.cats.models import UserCat, Cat

# ✅ سقف آفلاین: 12 ساعت
MAX_OFFLINE_SECONDS = 12 * 60 * 60


@dataclass
class OfflineIncomeResult:
    seconds_used: int
    earned: int
    rate_per_sec: float


async def calculate_offline_rate_per_sec(session, telegram_id: int) -> float:
    """
    نرخ تولید آفلاین کاربر را از روی گربه‌ها حساب می‌کند.
    هر گربه: base_meow_amount / base_meow_interval_sec
    """
    res = await session.execute(
        select(Cat.base_meow_amount, Cat.base_meow_interval_sec)
        .join(UserCat, UserCat.cat_id == Cat.id)
        .where(UserCat.user_telegram_id == telegram_id)
        .where(UserCat.is_alive == True)  # noqa: E712
        .where(UserCat.is_left == False)  # noqa: E712
    )
    rows = res.all()

    total = 0.0
    for amount, interval_sec in rows:
        if interval_sec and interval_sec > 0:
            total += float(amount) / float(interval_sec)

    return total


async def apply_offline_income(session, user: User) -> OfflineIncomeResult:
    """
    آفلاین را حساب می‌کند و به meow_points اضافه می‌کند.
    """
    now = datetime.now(timezone.utc)

    # اولین بار: last_claim_at ست می‌شود ولی درآمد نمی‌دهیم
    if user.last_claim_at is None:
        user.last_claim_at = now
        await session.commit()
        return OfflineIncomeResult(seconds_used=0, earned=0, rate_per_sec=0.0)

    diff = int((now - user.last_claim_at).total_seconds())
    if diff <= 0:
        return OfflineIncomeResult(seconds_used=0, earned=0, rate_per_sec=0.0)

    seconds_used = min(diff, MAX_OFFLINE_SECONDS)

    rate = await calculate_offline_rate_per_sec(session, user.telegram_id)

    earned = int(rate * seconds_used)

    # آپدیت کاربر
    user.meow_points += earned
    user.last_claim_at = now
    await session.commit()

    return OfflineIncomeResult(seconds_used=seconds_used, earned=earned, rate_per_sec=rate)
