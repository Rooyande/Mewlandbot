from aiogram import types
from aiogram.dispatcher import Dispatcher
from db.repo_users import get_or_create_user


def register(dp: Dispatcher):
    @dp.message_handler(commands=["start", "help"])
    async def start_cmd(message: types.Message):
        user_id = message.from_user.id
        username = message.from_user.username

        get_or_create_user(user_id, username)

        await message.reply(
            "✅ اسکلت ماژولار ساخته شد.\n"
            "مرحله بعد: هندلر mew + سرویس اقتصاد + ریپوهای cats."
        )

