from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.items.models import Item, UserItem


async def list_shop_items(session: AsyncSession) -> list[Item]:
    """
    لیست آیتم‌های فروشگاه (فقط active ها)
    """
    res = await session.execute(
        select(Item).where(Item.is_active == True).order_by(Item.id.asc())
    )
    return list(res.scalars().all())


async def get_user_items(session: AsyncSession, user_telegram_id: int) -> list[tuple[Item, int]]:
    """
    آیتم‌های کاربر را با تعدادشان برمی‌گرداند:
    خروجی: [(Item, qty), ...]
    """
    res = await session.execute(
        select(Item, UserItem.qty)
        .join(UserItem, UserItem.item_id == Item.id)
        .where(UserItem.user_telegram_id == user_telegram_id)
        .order_by(Item.id.asc())
    )
    return list(res.all())


async def buy_item(
    session: AsyncSession,
    user_telegram_id: int,
    item_id: int,
    user_meow_points: int,
) -> tuple[bool, str, int]:
    """
    خرید آیتم توسط کاربر

    ورودی:
    - session
    - user_telegram_id
    - item_id
    - user_meow_points: میزان meow point فعلی کاربر (از قبل گرفته شده)

    خروجی:
    (success, message, new_meow_points)
    """

    # آیتم وجود دارد؟
    item = await session.get(Item, item_id)
    if not item or not item.is_active:
        return False, "❌ Item not found or not active.", user_meow_points

    # پول کافی دارد؟
    if user_meow_points < item.price_meow:
        return False, "❌ Not enough Meow Points.", user_meow_points

    # آیا user_item قبلاً هست؟
    res = await session.execute(
        select(UserItem).where(
            UserItem.user_telegram_id == user_telegram_id,
            UserItem.item_id == item_id,
        )
    )
    user_item = res.scalar_one_or_none()

    if user_item:
        user_item.qty += 1
    else:
        user_item = UserItem(
            user_telegram_id=user_telegram_id,
            item_id=item_id,
            qty=1,
        )
        session.add(user_item)

    new_meow = user_meow_points - item.price_meow
    return True, f"✅ You bought {item.name}!", new_meow
