from datetime import datetime, timezone, timedelta

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from app.config.settings import settings
from app.infra.db.session import AsyncSessionLocal
from app.domain.users.service import get_or_create_user

router = Router()


def _is_private_and_not_admin(message: Message) -> bool:
    return (
        message.chat.type == "private"
        and message.from_user is not None
        and message.from_user.id != settings.admin_telegram_id
    )


def _is_allowed_group(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return True

    allowed = settings.allowed_chat_id_set()
    # اگر لیست خالی باشد یعنی همه گروه‌ها مجازند
    if not allowed:
        return True
    return message.chat.id in allowed


@router.message(CommandStart())
async def start(message: Message) -> None:
    if _is_private_and_not_admin(message):
        await message.answer("⛔ این بات فقط داخل گروه‌های مجاز فعال است.")
        return

    if not _is_allowed_group(message):
        return

    await message.answer(
        "✅ بات روشن است.\n🐾 در گروه‌های مجاز با گفتن **meow** امتیاز می‌گیری.",
        parse_mode="Markdown",
    )


@router.message(Command("profile"))
async def profile(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return

    if not _is_allowed_group(message):
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

    now = datetime.now(timezone.utc)
    cooldown = timedelta(minutes=7)

    if user.last_meow_at is None:
        cd_text = "آماده ✅"
    else:
        diff = now - user.last_meow_at
        if diff >= cooldown:
            cd_text = "آماده ✅"
        else:
            remaining = cooldown - diff
            mins = int(remaining.total_seconds() // 60)
            secs = int(remaining.total_seconds() % 60)
            cd_text = f"{mins}:{secs:02d}"

    # Placeholder برای آینده (وقتی cats table اضافه شد واقعی می‌کنیم)
    cats_count = 0
    best_cat = "نداری"

    username = f"@{user.username}" if user.username else "ندارد"
    created = user.created_at.strftime("%Y-%m-%d %H:%M")

    text = (
        "👤 پروفایل شما\n"
        "────────────\n"
        f"🆔 شناسه: `{user.telegram_id}`\n"
        f"🔗 یوزرنیم: {username}\n"
        f"🪙 Meow Points: **{user.meow_points}**\n"
        f"⏳ Cooldown: {cd_text}\n"
        "────────────\n"
        f"🐱 تعداد گربه‌ها: {cats_count}\n"
        f"🏆 بهترین گربه: {best_cat}\n"
        "────────────\n"
        f"📅 ساخته شده: {created} (UTC)\n"
    )

    await message.answer(text, parse_mode="Markdown")


@router.message()
async def handle_text(message: Message) -> None:
    if _is_private_and_not_admin(message):
        return

    if not _is_allowed_group(message):
        return

    txt = (message.text or "").strip().lower()

    if txt != "meow":
        return

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        now = datetime.now(timezone.utc)
        cooldown = timedelta(minutes=7)

        if user.last_meow_at is not None:
            diff = now - user.last_meow_at
            if diff < cooldown:
                remaining = cooldown - diff
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                await message.answer(f"⏳ هنوز کول‌داون داری.\n🕒 {mins}:{secs:02d} دیگه صبر کن.")
                return

        user.meow_points += 1
        user.last_meow_at = now
        await session.commit()

    await message.answer(
        f"🐾 **Meow!** ✅ +1 امتیاز گرفتی!\n"
        f"🪙 امتیاز فعلی: **{user.meow_points}**\n"
        f"⏳ کول‌داون: 7 دقیقه",
        parse_mode="Markdown",
    )
