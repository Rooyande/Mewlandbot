from aiogram import types
from aiogram.dispatcher import Dispatcher


def register(dp: Dispatcher):
    @dp.message_handler(commands=["start", "help"])
    async def start_cmd(message: types.Message):
        await message.reply(
            "😺 میولند\n\n"
            "دستورات:\n"
            "- mew (متنی) جمع کردن امتیاز با کول‌داون\n"
            "- /profile پروفایل\n"
            "- /adopt [rarity] خرید گربه\n"
            "- /cats لیست گربه‌ها\n"
            "- /leaderboard لیدربورد\n"
        )
