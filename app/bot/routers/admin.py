from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.filters.is_admin import IsAdmin

router = Router()


@router.message(IsAdmin(), Command("admin"))
async def admin_panel(message: Message) -> None:
    await message.answer(
        "پنل ادمین (نسخه اولیه)\n"
        "فعلاً فقط برای تست است.\n"
        "بعداً اینجا: مدیریت گروه‌های مجاز، شاپ، اقتصاد اضافه می‌شود."
    )
