from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message

from app.config.settings import settings
from app.infra.db.session import get_session
from app.domain.users.service import get_or_create_user
from app.domain.cats.service import (
    list_active_cats,
    buy_cat_for_user,
    list_user_cats,
    set_user_cat_name,
)

router = Router()


def _is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id == settings.ADMIN_TELEGRAM_ID


def _is_allowed_chat(chat_id: int) -> bool:
    return chat_id in settings.ALLOWED_CHAT_IDS


async def _deny_if_not_allowed(message: Message) -> bool:
    """
    True یعنی دسترسی رد شده و باید handler متوقف شود.
    """
    if message.chat.type == "private" and not _is_admin(message.from_user.id if message.from_user else None):
        await message.answer("بات فقط در گروه‌های مجاز فعال است.")
        return True

    if message.chat.type in ("group", "supergroup"):
        if not _is_allowed_chat(message.chat.id):
            return True

    return False


@router.message(F.text.startswith("/cats"))
async def cats_list(message: Message):
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
            f"{c.id}) {c.name} | rarity={c.rarity} | price={c.price_meow} | base={c.base_meow_amount}/{c.base_meow_interval_sec}s"
        )

    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/buycat"))
async def buycat(message: Message):
    if await _deny_if_not_allowed(message):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("فرمت صحیح: /buycat <cat_id>")
        return

    try:
        cat_id = int(parts[1].strip())
    except ValueError:
        await message.answer("cat_id باید عدد باشد. مثال: /buycat 1")
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username if message.from_user else None,
        )

        ok, msg = await buy_cat_for_user(session, user.telegram_id, cat_id)

    await message.answer(msg if msg else ("✅ خرید انجام شد." if ok else "❌ خرید انجام نشد."))


@router.message(F.text.startswith("/mycats"))
async def mycats(message: Message):
    """
    اینجا دقیقاً جایی بود که parse_mode=Markdown باعث crash می‌شد.
    ما plain text می‌فرستیم تا هیچ entity parsing رخ ندهد.
    """
    if await _deny_if_not_allowed(message):
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username if message.from_user else None,
        )

        cats = await list_user_cats(session, user.telegram_id)

    if not cats:
        await message.answer("هنوز گربه‌ای نداری. برای دیدن کاتالوگ: /cats")
        return

    lines = ["گربه‌های شما:"]
    for uc in cats:
        # حداقل اطلاعات قابل نمایش و بدون کاراکترهای خاص Markdown
        nickname = uc.nickname or "-"
        lines.append(
            f"#{uc.id} | {uc.cat.name} | rarity={uc.cat.rarity} | level={uc.level} | name={nickname}"
        )

    lines.append("")
    lines.append("برای نام‌گذاری: /setcatname <user_cat_id> <name>")
    await message.answer("\n".join(lines))


@router.message(F.text.startswith("/setcatname"))
async def setcatname_cmd(message: Message):
    if await _deny_if_not_allowed(message):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("فرمت صحیح: /setcatname <user_cat_id> <name>")
        return

    try:
        user_cat_id = int(parts[1].strip())
    except ValueError:
        await message.answer("user_cat_id باید عدد باشد. مثال: /setcatname 12 Mimo")
        return

    new_name = parts[2].strip()
    if not new_name:
        await message.answer("نام نمی‌تواند خالی باشد.")
        return

    # محدودیت ساده برای جلوگیری از اسپم/بهم ریختن UI
    if len(new_name) > 30:
        await message.answer("نام خیلی طولانی است. حداکثر ۳۰ کاراکتر.")
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session,
            message.from_user.id,
            message.from_user.username if message.from_user else None,
        )

        ok, msg = await set_user_cat_name(session, user.telegram_id, user_cat_id, new_name)

    await message.answer(msg if msg else ("✅ نام گربه تغییر کرد." if ok else "❌ تغییر نام انجام نشد."))
