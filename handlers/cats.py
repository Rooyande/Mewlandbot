from aiogram import types
from aiogram.dispatcher import Dispatcher

from db.repo_users import get_or_create_user
from services.cats import adopt_cat, get_my_cats_text


def register(dp: Dispatcher):
    @dp.message_handler(commands=["adopt"])
    async def adopt_cmd(message: types.Message):
        user_tg = message.from_user.id
        username = message.from_user.username
        rarity_arg = (message.get_args() or "").strip() or None

        res = adopt_cat(user_tg, username, rarity_arg)
        await message.reply(res.message)

    @dp.message_handler(commands=["cats"])
    async def cats_cmd(message: types.Message):
        user_tg = message.from_user.id
        username = message.from_user.username

        user_db_id = get_or_create_user(user_tg, username)
        text = get_my_cats_text(user_db_id)
        await message.reply(text)
