from aiogram import types
from aiogram.dispatcher import Dispatcher

from services.leaderboard import build_leaderboard_text


def register(dp: Dispatcher):
    @dp.message_handler(commands=["leaderboard"])
    async def leaderboard_cmd(message: types.Message):
        text = build_leaderboard_text(limit=10)
        await message.reply(text)
