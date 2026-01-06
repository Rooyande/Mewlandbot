from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from app.bot.filters.is_admin import IsAdmin
from app.infra.db.session import AsyncSessionLocal
from app.domain.users.models import User

router = Router()

ALLOWLIST_FILE = Path("allowed_chats.txt")


def _read_allowlist() -> set[int]:
    if not ALLOWLIST_FILE.exists():
        return set()
    out: set[int] = set()
    for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.add(int(line))
        except ValueError:
            continue
    return out


def _write_allowlist(values: set[int]) -> None:
    ALLOWLIST_FILE.write_text("\n".join(str(x) for x in sorted(values)), encoding="utf-8")


@router.message(IsAdmin(), Command("admin"))
async def admin_panel(message: Message) -> None:
    allowlist = _read_allowlist()
    await message.answer(
        "🛠 پنل ادمین\n\n"
        f"✅ گروه‌های مجاز: **{len(allowlist)}**\n\n"
        "📌 دستورها:\n"
        "➕ /allow <chat_id>          -> اضافه کردن گروه\n"
        "➖ /deny <chat_id>           -> حذف گروه\n"
        "📋 /list_allowed             -> نمایش لیست\n\n"
        "🪙 /addmeow <id|me> <amount> -> اضافه کردن امتیاز به کاربر\n"
        "مثال: /addmeow me 5000\n"
        "مثال: /addmeow 123456789 100\n\n"
        "ℹ️ نکته: chat_id گروه معمولاً با -100 شروع می‌شود.",
        parse_mode="Markdown",
    )


@router.message(IsAdmin(), Command("list_allowed"))
async def list_allowed(message: Message) -> None:
    allowlist = _read_allowlist()
    if not allowlist:
        await message.answer("📭 هیچ گروهی در لیست مجاز نیست.")
        return
    text = "📋 لیست گروه‌های مجاز:\n" + "\n".join(f"✅ {x}" for x in sorted(allowlist))
    await message.answer(text)


@router.message(IsAdmin(), Command("allow"))
async def allow_chat(message: Message) -> None:
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("⚠️ فرمت درست: `/allow <chat_id>`", parse_mode="Markdown")
        return

    try:
        chat_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ chat_id باید عدد باشد.")
        return

    allowlist = _read_allowlist()
    allowlist.add(chat_id)
    _write_allowlist(allowlist)
    await message.answer(f"✅ اضافه شد: `{chat_id}`", parse_mode="Markdown")


@router.message(IsAdmin(), Command("deny"))
async def deny_chat(message: Message) -> None:
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer("⚠️ فرمت درست: `/deny <chat_id>`", parse_mode="Markdown")
        return

    try:
        chat_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ chat_id باید عدد باشد.")
        return

    allowlist = _read_allowlist()
    if chat_id in allowlist:
        allowlist.remove(chat_id)
        _write_allowlist(allowlist)
        await message.answer(f"✅ حذف شد: `{chat_id}`", parse_mode="Markdown")
        return

    await message.answer("ℹ️ این chat_id در لیست نبود.")


@router.message(IsAdmin(), Command("addmeow"))
async def addmeow(message: Message) -> None:
    """
    /addmeow <telegram_id|me> <amount>
    """
    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        await message.answer(
            "⚠️ فرمت درست:\n"
            "`/addmeow me 5000`\n"
            "`/addmeow 123456789 100`",
            parse_mode="Markdown",
        )
        return

    target_raw = parts[1].strip().lower()
    amount_raw = parts[2].strip()

    try:
        amount = int(amount_raw)
    except ValueError:
        await message.answer("⚠️ amount باید عدد باشد.")
        return

    if amount <= 0:
        await message.answer("⚠️ amount باید بزرگتر از صفر باشد.")
        return

    if target_raw == "me":
        target_id = message.from_user.id
    else:
        try:
            target_id = int(target_raw)
        except ValueError:
            await message.answer("⚠️ telegram_id باید عدد باشد یا me.")
            return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.telegram_id == target_id))
        user = res.scalar_one_or_none()

        if not user:
            # اگر کاربر هنوز وارد DB نشده بود، بسازیم
            user = User(telegram_id=target_id, username=None, meow_points=0)
            session.add(user)
            await session.commit()
            await session.refresh(user)

        user.meow_points += amount
        await session.commit()

    await message.answer(
        f"✅ انجام شد!\n"
        f"🆔 کاربر: `{target_id}`\n"
        f"🪙 اضافه شد: **{amount}**\n"
        f"🪙 امتیاز فعلی: **{user.meow_points}**",
        parse_mode="Markdown",
    )
