# app/bot/routers/public.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery

# DB session maker (adjust path if your project differs)
from app.infra.db.session import async_session_maker  # <-- اگر مسیرش فرق دارد، همین را اصلاح کن

# Services (adjust paths if needed)
from app.domain.users.service import get_or_create_user  # expects (session, tg_id, username)
from app.domain.cats.service import (
    meow_click,             # (session, user_id or tg_id) -> updated user snapshot
    get_profile,            # (session, user_id or tg_id) -> profile dto
    open_cat_shop,          # (session, user_id or tg_id) -> shop dto (cats)
    buy_cat,                # (session, user_id or tg_id, cat_id) -> result dto
)
from app.domain.items.service import (
    open_item_shop,         # (session, user_id or tg_id) -> shop dto (items)
    buy_item,               # (session, user_id or tg_id, item_id) -> result dto
)

from app.domain.economy.offline_income import apply_offline_income  # (session, user_id or tg_id, now=...) -> income dto


router = Router()


def _safe_username(message: Message) -> str:
    """
    Ensure we always pass a username string to get_or_create_user.
    Priority: @username -> full_name -> first_name -> fallback by id
    """
    u = message.from_user
    if not u:
        return "unknown"
    if u.username:
        return f"@{u.username}"
    full = (u.full_name or "").strip()
    if full:
        return full
    first = (u.first_name or "").strip()
    if first:
        return first
    return f"user_{u.id}"


async def _ensure_user(session, message: Message):
    tg_id = message.from_user.id
    username = _safe_username(message)
    return await get_or_create_user(session, tg_id, username)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# -------------------------
# Commands
# -------------------------

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _ensure_user(session, message)

        # Apply offline income on entry (so profile/meow feels consistent)
        try:
            await apply_offline_income(session, user.tg_id, now=_now_utc())
        except Exception:
            # Do not crash user experience if offline calc fails
            pass

        text = (
            "🐾 خوش اومدی به Meow Bot!\n\n"
            "✅ دستورهای اصلی:\n"
            "• /meow — کلیک و گرفتن امتیاز\n"
            "• /profile — پروفایل و درآمد\n"
            "• /shop — خرید گربه‌ها\n"
            "• /items — خرید آیتم‌ها\n"
            "• /help — راهنما\n\n"
            "برای شروع، /meow رو بزن."
        )
        await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "📌 راهنمای Meow Bot\n\n"
        "🐾 عمومی:\n"
        "• /start — شروع\n"
        "• /help — همین راهنما\n\n"
        "🎮 گیم‌پلی:\n"
        "• /meow — گرفتن Meow Points\n"
        "• /profile — نمایش پروفایل، تعداد گربه‌ها، درآمد (mps)\n\n"
        "🛒 فروشگاه:\n"
        "• /shop — فروشگاه گربه‌ها\n"
        "• /items — فروشگاه آیتم‌ها\n\n"
        "نکته: درآمد آفلاین به‌صورت خودکار هنگام ورود/پروفایل اعمال می‌شود. 🧮"
    )
    await message.answer(text)


@router.message(Command("meow"))
async def cmd_meow(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _ensure_user(session, message)

        # Apply offline income before click so numbers feel correct
        try:
            await apply_offline_income(session, user.tg_id, now=_now_utc())
        except Exception:
            pass

        result = await meow_click(session, user.tg_id)

        # Keep message plain text to avoid Markdown entity crashes
        text = (
            "😺 Meow!\n"
            f"➕ +{getattr(result, 'earned', 1)} امتیاز\n"
            f"💰 موجودی: {getattr(result, 'balance', '—')}\n"
        )
        await message.answer(text)


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _ensure_user(session, message)

        income = None
        try:
            income = await apply_offline_income(session, user.tg_id, now=_now_utc())
        except Exception:
            pass

        prof = await get_profile(session, user.tg_id)

        # Expected fields (adapt in your service DTOs):
        balance = getattr(prof, "balance", "—")
        cats_count = getattr(prof, "cats_count", "—")
        mps = getattr(prof, "meow_per_second", getattr(prof, "mps", "—"))

        offline_added = getattr(income, "added", None) if income else None

        text = (
            "👤 پروفایل\n\n"
            f"🆔 {user.tg_id}\n"
            f"💰 Meow Points: {balance}\n"
            f"🐱 تعداد گربه‌ها: {cats_count}\n"
            f"⏱️ Meow/sec: {mps}\n"
        )
        if offline_added is not None:
            text += f"\n📦 درآمد آفلاین اضافه شد: {offline_added}\n"

        await message.answer(text)


@router.message(Command("shop"))
async def cmd_shop(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _ensure_user(session, message)
        shop = await open_cat_shop(session, user.tg_id)

        # If your shop returns list of cats, render a simple list.
        cats = getattr(shop, "cats", [])
        if not cats:
            await message.answer("🛒 فروشگاه گربه‌ها خالیه یا سرویسش درست برنگشته.")
            return

        lines = ["🛒 فروشگاه گربه‌ها", ""]
        for c in cats:
            cid = getattr(c, "id", "?")
            name = getattr(c, "name", "Cat")
            rarity = getattr(c, "rarity", "")
            price = getattr(c, "price", "")
            mps = getattr(c, "mps", getattr(c, "meow_per_second", ""))
            lines.append(f"🐾 #{cid} | {name} | {rarity} | 💰{price} | ⏱️{mps}")

        lines.append("")
        lines.append("برای خرید: دستور زیر را بزن")
        lines.append("مثال: /buycat 3")

        await message.answer("\n".join(lines))


@router.message(Command("items"))
async def cmd_items(message: Message) -> None:
    async with async_session_maker() as session:
        user = await _ensure_user(session, message)
        shop = await open_item_shop(session, user.tg_id)

        items = getattr(shop, "items", [])
        if not items:
            await message.answer("🧰 فروشگاه آیتم‌ها خالیه یا سرویسش درست برنگشته.")
            return

        lines = ["🧰 فروشگاه آیتم‌ها", ""]
        for it in items:
            iid = getattr(it, "id", "?")
            name = getattr(it, "name", "Item")
            desc = getattr(it, "description", "")
            price = getattr(it, "price", "")
            bonus = getattr(it, "bonus", getattr(it, "mps_bonus", ""))
            lines.append(f"🧩 #{iid} | {name} | 💰{price} | ⭐{bonus}")
            if desc:
                lines.append(f"   └ {desc}")

        lines.append("")
        lines.append("برای خرید: دستور زیر را بزن")
        lines.append("مثال: /buyitem 5")

        await message.answer("\n".join(lines))


@router.message(Command("buycat"))
async def cmd_buycat(message: Message) -> None:
    """
    Usage: /buycat <cat_id>
    """
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("❗️فرمت درست: /buycat 3")
        return

    cat_id = int(parts[1])

    async with async_session_maker() as session:
        user = await _ensure_user(session, message)
        result = await buy_cat(session, user.tg_id, cat_id)

        ok = getattr(result, "ok", getattr(result, "success", True))
        msg = getattr(result, "message", None)

        if ok:
            await message.answer(f"✅ خرید انجام شد. 🐱\n{msg or ''}".strip())
        else:
            await message.answer(f"❌ خرید ناموفق بود.\n{msg or 'موجودی کافی نیست یا آیتم پیدا نشد.'}")


@router.message(Command("buyitem"))
async def cmd_buyitem(message: Message) -> None:
    """
    Usage: /buyitem <item_id>
    """
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("❗️فرمت درست: /buyitem 5")
        return

    item_id = int(parts[1])

    async with async_session_maker() as session:
        user = await _ensure_user(session, message)
        result = await buy_item(session, user.tg_id, item_id)

        ok = getattr(result, "ok", getattr(result, "success", True))
        msg = getattr(result, "message", None)

        if ok:
            await message.answer(f"✅ خرید انجام شد. 🧩\n{msg or ''}".strip())
        else:
            await message.answer(f"❌ خرید ناموفق بود.\n{msg or 'موجودی کافی نیست یا آیتم پیدا نشد.'}")


# -------------------------
# Optional: fallback text handler (if you had "tap to meow" behavior)
# -------------------------

@router.message(F.text)
async def handle_text_fallback(message: Message) -> None:
    """
    If you want any plain text (e.g. "meow") to trigger /meow,
    keep it here. Otherwise, remove this handler.
    """
    txt = (message.text or "").strip().lower()
    if txt in {"meow", "mew", "میو", "میو!", "meow!"}:
        await cmd_meow(message)
        return

    # default guidance
    await message.answer("برای راهنما /help رو بزن. 🐾")
