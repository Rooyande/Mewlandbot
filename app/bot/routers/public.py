from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config.settings import settings
from app.domain.users.service import get_or_create_user
from app.domain.cats.service import get_user_cats
from app.domain.items.service import list_shop_items, buy_item, get_user_items
from app.domain.economy.rate_service import calculate_user_rate
from app.domain.economy.offline_income import apply_offline_income

from app.infra.db.session import AsyncSessionLocal


router = Router()


def _is_private_chat(message: Message) -> bool:
    return message.chat.type == "private"


def _is_allowed_group(message: Message) -> bool:
    if message.chat.id is None:
        return False
    return str(message.chat.id) in settings.allowed_chat_ids


# -------------------------
# /start , /help
# -------------------------

@router.message(Command("start"))
async def start(message: Message) -> None:
    text = (
        "👋 سلام! به Meowland خوش اومدی.\n\n"
        "📌 تو گروه‌های مجاز با گفتن `meow` می‌تونی امتیاز جمع کنی.\n"
        "🐾 با امتیاز می‌تونی گربه بخری و آیتم بگیری.\n\n"
        "✅ برای دیدن همه دستورها: /help"
    )
    await message.answer(text)


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    # فعلاً ساده؛ آخر کار کامل و حرفه‌ای می‌کنیم (طبق خواسته‌ات)
    text = (
        "📖 راهنمای دستورات:\n\n"
        "👤 /profile — پروفایل و امتیازها\n"
        "🐱 /mycats — لیست گربه‌های تو\n"
        "🛒 /shop — فروشگاه آیتم‌ها\n"
        "🧺 /myitems — آیتم‌های تو\n"
        "💰 /mps — نرخ تولید meow/sec\n"
        "⏳ /claim — دریافت درآمد آفلاین\n"
        "🧾 /buycat — لیست خرید گربه‌ها\n"
        "✅ /buycat <id> — خرید گربه\n"
        "✅ /buyitem <id> — خرید آیتم\n"
    )
    await message.answer(text)


# -------------------------
# MEOW Message (Group only)
# -------------------------

@router.message()
async def handle_meow(message: Message) -> None:
    text = (message.text or "").strip().lower()

    # فقط گروه‌های مجاز
    if message.chat.type in ("group", "supergroup"):
        if not _is_allowed_group(message):
            return

        if text != "meow":
            return

        async with AsyncSessionLocal() as session:
            user = await get_or_create_user(session, message.from_user.id)

            now = datetime.now(timezone.utc)
            if user.last_meow_at is not None:
                diff = (now - user.last_meow_at).total_seconds()
                if diff < 7 * 60:
                    left = int((7 * 60) - diff)
                    await message.reply(f"⏳ هنوز زوده! {left} ثانیه دیگه دوباره meow کن 😼")
                    return

            user.meow_points += 1
            user.last_meow_at = now
            await session.commit()

        await message.reply("✅ +1 Meow Point 😺")
        return

    # جلوگیری از کارکرد در پیوی (در آینده میشه مدیریتش کرد)
    if _is_private_chat(message):
        return


# -------------------------
# /profile
# -------------------------

@router.message(Command("profile"))
async def profile(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)

        cats = await get_user_cats(session, user.telegram_id)
        items = await get_user_items(session, user.telegram_id)

        breakdown = await calculate_user_rate(session, user.telegram_id)

        text = (
            f"👤 پروفایل شما\n\n"
            f"🆔 ID: `{user.telegram_id}`\n"
            f"💰 Meow Points: `{user.meow_points}`\n"
            f"🐱 تعداد گربه‌ها: `{len(cats)}`\n"
            f"🎒 تعداد آیتم‌ها: `{sum(i.quantity for i in items) if items else 0}`\n\n"
            f"⚡ تولید (Meow/sec): `{breakdown.final_per_sec:.6f}`\n"
            f"   🐾 Base: `{breakdown.base_per_sec:.6f}`\n"
            f"   ➕ Flat: `{breakdown.flat_bonus_per_sec:.6f}`\n"
            f"   ✖️ Mult: `{breakdown.multiplier:.3f}`\n"
        )
    await message.answer(text, parse_mode="Markdown")


# -------------------------
# /mps
# -------------------------

@router.message(Command("mps"))
async def mps(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        breakdown = await calculate_user_rate(session, user.telegram_id)

    per_sec = breakdown.final_per_sec
    per_min = per_sec * 60
    per_hour = per_min * 60

    text = (
        "⚡ نرخ تولید شما\n\n"
        f"🐾 Meow/sec: `{per_sec:.6f}`\n"
        f"🕐 Meow/min: `{per_min:.4f}`\n"
        f"🕓 Meow/hour: `{per_hour:.2f}`\n\n"
        f"📌 Base: `{breakdown.base_per_sec:.6f}`\n"
        f"➕ Flat: `{breakdown.flat_bonus_per_sec:.6f}`\n"
        f"✖️ Mult: `{breakdown.multiplier:.3f}`\n"
    )
    await message.answer(text, parse_mode="Markdown")


# -------------------------
# /claim
# -------------------------

@router.message(Command("claim"))
async def claim(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        result = await apply_offline_income(session, user)

    if result.seconds_used <= 0:
        await message.answer("⏳ هنوز چیزی برای claim نداری 😿")
        return

    await message.answer(
        f"✅ Claim شد!\n\n"
        f"⏱ مدت: `{result.seconds_used}` ثانیه\n"
        f"⚡ Rate: `{result.rate_per_sec:.6f}` meow/sec\n"
        f"💰 درآمد: `{result.earned}` Meow Points 😺",
        parse_mode="Markdown",
    )


# -------------------------
# Cats
# -------------------------

@router.message(Command("mycats"))
async def mycats(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        cats = await get_user_cats(session, user.telegram_id)

    if not cats:
        await message.answer("😿 هیچ گربه‌ای نداری. با /buycat یکی بخر.")
        return

    lines = ["🐱 گربه‌های شما:\n"]
    for uc in cats:
        nickname = uc.nickname or uc.cat.name
        lines.append(f"• `{uc.id}` — {nickname} ({uc.cat.rarity}) lvl {uc.level} 😺")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("buycat"))
async def buycat_list(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        from app.domain.cats.service import list_available_cats  # local import
        cats = await list_available_cats(session)

    if not cats:
        await message.answer("😿 فعلاً گربه‌ای برای فروش نیست.")
        return

    lines = ["🧾 لیست گربه‌ها برای خرید:\n"]
    for c in cats:
        lines.append(f"• `{c.id}` — {c.name} ({c.rarity}) 🪙 `{c.price_meow}`")

    lines.append("\n✅ خرید: `/buycat <id>`")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("buycat"))
async def buycat_execute(message: Message) -> None:
    # اگر فقط /buycat بود، handler بالا اجرا میشه.
    # این handler زمانی اجرا میشه که آرگومان داشته باشه.
    parts = (message.text or "").split()
    if len(parts) == 1:
        return

    try:
        cat_id = int(parts[1])
    except ValueError:
        await message.answer("❌ فرمت غلطه. مثال: `/buycat 3`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        from app.domain.cats.service import buy_cat  # local import

        ok, msg = await buy_cat(session, user.telegram_id, cat_id)

    await message.answer(msg)


# -------------------------
# Shop Items
# -------------------------

@router.message(Command("shop"))
async def shop(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        items = await list_shop_items(session)

    if not items:
        await message.answer("🛒 فروشگاه خالیه 😿")
        return

    lines = ["🛒 فروشگاه آیتم‌ها:\n"]
    for it in items:
        lines.append(f"• `{it.id}` — {it.name} 🪙 `{it.price_meow}` ({it.effect_type}:{it.effect_value})")

    lines.append("\n✅ خرید: `/buyitem <id>`")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("buyitem"))
async def buyitem_cmd(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("❌ مثال: `/buyitem 2`", parse_mode="Markdown")
        return

    try:
        item_id = int(parts[1])
    except ValueError:
        await message.answer("❌ آیتم ID باید عدد باشه.", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        ok, msg = await buy_item(session, user.telegram_id, item_id)

    await message.answer(msg)


@router.message(Command("myitems"))
async def myitems(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        items = await get_user_items(session, user.telegram_id)

    if not items:
        await message.answer("🎒 هیچ آیتمی نداری 😿")
        return

    lines = ["🎒 آیتم‌های شما:\n"]
    for ui in items:
        lines.append(f"• {ui.item.name} x{ui.quantity} ✅")

    await message.answer("\n".join(lines))
