from aiogram.filters import BaseFilter
from aiogram.types import Message

from app.config.settings import settings


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id == settings.admin_telegram_id)
