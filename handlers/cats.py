from aiogram import types
from aiogram.dispatcher import Dispatcher

from db.repo_users import get_or_create_user
from services.cats import adopt_cat, get_my_cats_text, feed_cat, play_cat


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

    @dp.message_handler(commands=["feed"])
    async def feed_cmd(message: types.Message):
        user_tg = message.from_user.id
        username = message.from_user.username

        args = (message.get_args() or "").split()
        if len(args) != 2:
            await message.reply("❌ فرمت: /feed <cat_id> <amount>")
            return

        try:
            cat_id = int(args[0])
            amount = int(args[1])
        except ValueError:
            await message.reply("❌ cat_id و amount باید عدد باشند.")
            return

        res = feed_cat(user_tg, username, cat_id, amount)
        await message.reply(res.message)

    @dp.message_handler(commands=["play"])
    async def play_cmd(message: types.Message):
        user_tg = message.from_user.id
        username = message.from_user.username

        args = (message.get_args() or "").split()
        if len(args) != 1:
            await message.reply("❌ فرمت: /play <cat_id>")
            return

        try:
            cat_id = int(args[0])
        except ValueError:
            await message.reply("❌ cat_id باید عدد باشد.")
            return

        res = play_cat(user_tg, username, cat_id)
        await message.reply(res.message)
