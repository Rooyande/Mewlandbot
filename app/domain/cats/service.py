from __future__ import annotations

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.cats.models import Cat, UserCat


# ------------------------------
# Catalog
# ------------------------------

async def get_active_cats(session: AsyncSession) -> list[Cat]:
    q = select(Cat).where(Cat.is_active.is_(True)).order_by(Cat.id)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_cat_by_id(session: AsyncSession, cat_id: int) -> Cat | None:
    q = select(Cat).where(Cat.id == cat_id)
    res = await session.execute(q)
    return res.scalar_one_or_none()


# ------------------------------
# User Cats
# ------------------------------

async def get_user_cats(session: AsyncSession, user_telegram_id: int) -> list[UserCat]:
    """
    لیست گربه‌های کاربر (مالکیت واقعی، نه کاتالوگ)
    """
    q = (
        select(UserCat)
        .where(UserCat.user_telegram_id == user_telegram_id)
        .order_by(UserCat.id.desc())
    )
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_user_cat_count(session: AsyncSession, user_telegram_id: int) -> int:
    q = select(func.count(UserCat.id)).where(UserCat.user_telegram_id == user_telegram_id)
    res = await session.execute(q)
    return int(res.scalar() or 0)


async def add_cat_to_user(
    session: AsyncSession,
    user_telegram_id: int,
    cat_id: int,
    nickname: str | None = None,
) -> UserCat:
    """
    اضافه کردن یک گربه به کاربر
    """
    user_cat = UserCat(
        user_telegram_id=user_telegram_id,
        cat_id=cat_id,
        nickname=nickname,
        level=1,
        happiness=100,
        hunger=0,
        is_alive=True,
        is_left=False,
    )

    session.add(user_cat)
    await session.commit()
    await session.refresh(user_cat)
    return user_cat


async def rename_user_cat(
    session: AsyncSession,
    user_telegram_id: int,
    user_cat_id: int,
    new_name: str,
) -> bool:
    """
    تغییر اسم یک گربه از طرف کاربر
    """
    q = (
        update(UserCat)
        .where(
            UserCat.id == user_cat_id,
            UserCat.user_telegram_id == user_telegram_id,
            UserCat.is_alive.is_(True),
            UserCat.is_left.is_(False),
        )
        .values(nickname=new_name.strip()[:64])
    )
    res = await session.execute(q)
    await session.commit()
    return res.rowcount > 0


async def get_user_cat_by_id(
    session: AsyncSession,
    user_telegram_id: int,
    user_cat_id: int,
) -> UserCat | None:
    q = (
        select(UserCat)
        .where(
            UserCat.id == user_cat_id,
            UserCat.user_telegram_id == user_telegram_id,
        )
    )
    res = await session.execute(q)
    return res.scalar_one_or_none()


# ------------------------------
# Helper: income-related
# ------------------------------

async def get_user_total_meow_rate(session: AsyncSession, user_telegram_id: int) -> float:
    """
    مجموع نرخ تولید meow از تمام گربه‌های کاربر (meow per second)
    فرمول: sum(base_meow_amount / base_meow_interval_sec)
    """
    q = (
        select(
            func.coalesce(
                func.sum(Cat.base_meow_amount.cast(func.float) / Cat.base_meow_interval_sec),
                0.0,
            )
        )
        .select_from(UserCat)
        .join(Cat, Cat.id == UserCat.cat_id)
        .where(
            UserCat.user_telegram_id == user_telegram_id,
            UserCat.is_alive.is_(True),
            UserCat.is_left.is_(False),
        )
    )
    res = await session.execute(q)
    return float(res.scalar() or 0.0)
