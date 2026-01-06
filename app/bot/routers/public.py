from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.config.settings import settings

router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    # جلوگیری از کار در پیوی برای غیر ادمین
    if message.chat.type == "private" and message.from_user and message.from_user.id != settings.admin_telegram_id:
        await message.answer("این بات فقط داخل گروه‌های مجاز فعال است.")
        return

    await message.answer("بات روشن است. در گروه‌های مجاز با گفتن meow امتیاز می‌گیری.")


@router.message()
async def gate_private_and_allowlist(message: Message) -> None:
    # جلوگیری از کار در پیوی برای غیر ادمین
    if message.chat.type == "private" and message.from_user and message.from_user.id != settings.admin_telegram_id:
        return

    # فقط گروه‌های مجاز
    if message.chat.type in ("group", "supergroup"):
        allowed = settings.allowed_chat_id_set()
        if allowed and message.chat.id not in allowed:
            return

    # فعلاً فقط یک رفتار نمایشی: اگر meow گفت
    txt = (message.text or "").strip().lower()
    if txt == "meow":
        await message.answer("meow ثبت شد (نسخه اولیه).")
