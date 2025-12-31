from aiogram import types
from aiogram.dispatcher import Dispatcher

from services.achievements import achievements_show


def register(dp: Dispatcher):
    @dp.message_handler(commands=["achievements"])
    async def achievements_cmd(message: types.Message):
        res = achievements_show(message.from_user.id, message.from_user.username)
        await message.reply(res.message)
