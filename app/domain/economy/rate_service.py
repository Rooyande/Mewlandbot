from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import func, select

from app.domain.cats.models import UserCat, Cat
from app.domain.items.models import UserItem, Item


@dataclass
class RateBreakdown:
    base_per_sec: float
    flat_bonus_per_sec: float
    multiplier: float
    final_per_sec: float


async def calculate_user_rate(session, telegram_id: int) -> RateBreakdown:
    """
    نرخ تولید کاربر را از روی:
    - گربه‌ها (base)
    - آیتم‌ها (flat + multiplier)
    حساب می‌کند و breakdown می‌دهد.
    """

    # 1) Base rate از روی گربه‌ها
    res = await session.execute(
        select(Cat.base_meow_amount, Cat.base_meow_interval_sec)
        .join(UserCat, UserCat.cat_id == Cat.id)
        .where(UserCat.user_telegram_id == telegram_id)
        .where(UserCat.is_alive == True)  # noqa: E712
        .where(UserCat.is_left == False)  # noqa: E712
    )
    rows = res.all()

    base_per_sec = 0.0
    for amount, interval_sec in rows:
        if interval_sec and interval_sec > 0:
            base_per_sec += float(amount) / float(interval_sec)

    # 2) Flat bonus و multiplier از روی آیتم‌ها
    res2 = await session.execute(
        select(Item.effect_type, Item.effect_value, func.sum(UserItem.quantity))
        .join(UserItem, UserItem.item_id == Item.id)
        .where(UserItem.user_telegram_id == telegram_id)
        .where(Item.is_active == True)  # noqa: E712
        .group_by(Item.effect_type, Item.effect_value)
    )
    item_rows = res2.all()

    flat_bonus_per_sec = 0.0
    multiplier = 1.0

    for effect_type, effect_value, qty in item_rows:
        qty = int(qty or 0)
        if qty <= 0:
            continue

        if effect_type == "mps_flat":
            flat_bonus_per_sec += float(effect_value) * qty

        elif effect_type == "mps_multiplier":
            # multiplier stacking:
            # اگر effect_value=1.10 و qty=2 → (1.10 ^ 2)
            multiplier *= float(effect_value) ** qty

    final_per_sec = (base_per_sec + flat_bonus_per_sec) * multiplier

    return RateBreakdown(
        base_per_sec=base_per_sec,
        flat_bonus_per_sec=flat_bonus_per_sec,
        multiplier=multiplier,
        final_per_sec=final_per_sec,
    )
