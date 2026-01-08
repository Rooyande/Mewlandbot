from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message

from app.config.settings import settings
from app.infra.db.session import get_session
from app.domain.users.service import get_or_create_user
from app.domain.economy.offline_income import claim_offline_income
from app.domain.economy.rate_service import compute_user_rate
from app.domain.cats.service import list_active_cats
from app.domain.items.service import list_active_items

router = Router()


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id == settings.ADMIN_TELEGRAM_ID


def _is_allowed_chat(chat_id: int) -> bool:
    # اگر شما allowlist را در DB هم دارید، اینجا بعداً می‌شود جایگزین/ادغام کرد.
    # فعلاً از settings.ALLOWED_CHAT_IDS استفاده می‌کنیم.
    return chat_id in settings.ALLOWED_CHAT_IDS


async def _deny_if_not_allowed(message: Message) -> bool:
    """
    True یعنی دسترسی رد شده و باید handler متوقف شود.
    """
    # PV برای غیرادمین: هیچ چیزی جواب نده یا پیام کوتاه بده (با تصمیم شما)
    if message.chat.type == "private" and not _is_admin(message.from_user.id if message.from_user else None):
        # اگر می‌خواهی کاملاً ignore کند:
        # return True
        await message.answer("بات فقط در گروه‌های مجاز فعال است.")
        return True

    # گروه‌ها: فقط allowlist
    if message.chat.type in ("group", "supergroup"):
        if not _is_allowed_chat(message.chat.id):
            return True

    return False


@router.message(F.text.startswith("/start"))
async def start(message: Message):
    if await _deny_if_not_allowed(message):
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username if message.from_user else None,
        )

    await message.answer(
        "سلام. به Meowland خوش آمدی.\n"
        "برای دیدن دستورات: /help\n"
        "برای پروفایل: /profile\n"
        "برای درآمد آفلاین: /claim\n"
    )


@router.message(F.text.startswith("/help"))
async def help_cmd(message: Message):
    if await _deny_if_not_allowed(message):
        return

    await message.answer(
        "دستورات عمومی:\n"
        "/profile - نمایش پروفایل\n"
        "/cats - لیست گربه‌ها\n"
        "/buycat <id> - خرید گربه\n"
        "/mycats - لیست گربه‌های من\n"
        "/setcatname <user_cat_id> <name> - نام‌گذاری گربه\n"
        "/shop - لیست آیتم‌ها\n"
        "/buyitem <id> - خرید آیتم\n"
        "/myitems - لیست آیتم‌های من\n"
        "/claim - دریافت درآمد آفلاین\n\n"
        "اکتیو Earn:\n"
        "در گروه بنویس: meow\n"
    )


@router.message(F.text.startswith("/profile"))
async def profile(message: Message):
    if await _deny_if_not_allowed(message):
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username if message.from_user else None,
        )

        rate = await compute_user_rate(session, user.telegram_id)

    await message.answer(
        f"پروفایل شما:\n"
        f"Meow Points: {user.meow_points}\n"
        f"Rate: {rate:.4f} meow/sec\n"
        f"برای دریافت درآمد آفلاین: /claim\n"
    )


@router.message(F.text.lower() == "meow")
async def handle_meow(message: Message):
    if await _deny_if_not_allowed(message):
        return

    async with get_session() as session:
        # ✅ فیکس اصلی: username پاس داده می‌شود
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username if message.from_user else None,
        )

        # این تابع را قبلاً داخل users.service دارید (یا در همین handler پیاده کردید).
        # ما فرض می‌کنیم یک متد در user service دارید که cooldown و increment را انجام می‌دهد.
        # اگر ندارید، باید مطابق کد خودتان جایگزین شود.
        from app.domain.users.service import apply_meow_gain

        gained, cooldown_left = await apply_meow_gain(session, user.telegram_id)

    if gained > 0:
        await message.answer(f"✅ +{gained} Meow Points")
    else:
        await message.answer(f"⏳ هنوز cooldown داری. {cooldown_left} ثانیه دیگر.")


@router.message(F.text.startswith("/cats"))
async def cats_cmd(message: Message):
    if await _deny_if_not_allowed(message):
        return

    async with get_session() as session:
        cats = await list_active_cats(session)

    if not cats:
        await message.answer("فعلاً گربه فعالی وجود ندارد.")
        return

    lines = ["گربه‌های فعال:"]
    for c in cats:
        lines.append(
            f"{c.id}) {c.name} [{c.rarity}] - قیمت: {c.price_meow} - تولید پایه: {c.base_meow_amount}/{c.base_meow_interval_sec}s"
        )
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/shop"))
async def shop_cmd(message: Message):
    if await _deny_if_not_allowed(message):
        return

    async with get_session() as session:
        items = await list_active_items(session)

    if not items:
        await message.answer("فعلاً آیتم فعالی وجود ندارد.")
        return

    lines = ["آیتم‌های فعال:"]
    for it in items:
        lines.append(f"{it.id}) {it.name} - قیمت: {it.price_meow}")
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/claim"))
async def claim_cmd(message: Message):
    if await _deny_if_not_allowed(message):
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username if message.from_user else None,
        )

        gained, seconds = await claim_offline_income(session, user.telegram_id)

    if gained <= 0:
        await message.answer("فعلاً چیزی برای claim نداری.")
        return

    await message.answer(
        f"✅ درآمد آفلاین دریافت شد.\n"
        f"+{gained} Meow Points\n"
        f"(مدت محاسبه: {seconds} ثانیه)"
    )
