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
    # اگر لیست خالی باشد یعنی همه گروه‌ها مجازند (می‌توانی برعکسش هم کنی، ولی فعلاً این ساده‌تر است)
    if not allowed:
        return True
    return message.chat.id in allowed


@router.message(CommandStart())
async def start(message: Message) -> None:
    if _is_private_and_not_admin(message):
        await message.answer("این بات فقط داخل گروه‌های مجاز فعال است.")
        return

    if not _is_allowed_group(message):
        return

    await message.answer("بات روشن است. در گروه‌های مجاز با گفتن meow امتیاز می‌گیری.")


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

    await message.answer(
        "پروفایل شما\n"
        f"Meow Points: {user.meow_points}\n"
        f"User: @{user.username or 'unknown'}"
    )


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
                await message.answer(f"هنوز کول‌داون داری. {mins}:{secs:02d} دیگه صبر کن.")
                return

        user.meow_points += 1
        user.last_meow_at = now
        await session.commit()

    await message.answer("✅ +1 Meow Point گرفتی!")
