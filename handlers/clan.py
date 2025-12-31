from aiogram import types
from aiogram.dispatcher import Dispatcher

from services.clans import (
    clan_help_text,
    clan_create,
    clan_join,
    clan_leave,
    clan_members,
    clan_list,
    clan_info_by_name,
    clan_bonus,
)


def register(dp: Dispatcher):
    @dp.message_handler(commands=["clan"])
    async def clan_cmd(message: types.Message):
        args = (message.get_args() or "").split()
        if not args:
            await message.reply(clan_help_text())
            return

        sub = args[0].lower()

        if sub == "create":
            if len(args) < 2:
                await message.reply("❌ فرمت: /clan create <name>")
                return
            name = " ".join(args[1:])
            res = clan_create(message.from_user.id, message.from_user.username, name)
            await message.reply(res.message)
            return

        if sub == "join":
            if len(args) < 2:
                await message.reply("❌ فرمت: /clan join <name>")
                return
            name = " ".join(args[1:])
            res = clan_join(message.from_user.id, message.from_user.username, name)
            await message.reply(res.message)
            return

        if sub == "leave":
            res = clan_leave(message.from_user.id, message.from_user.username)
            await message.reply(res.message)
            return

        if sub == "members":
            res = clan_members(message.from_user.id, message.from_user.username)
            await message.reply(res.message)
            return

        if sub == "list":
            res = clan_list()
            await message.reply(res.message)
            return

        if sub == "info":
            if len(args) < 2:
                await message.reply("❌ فرمت: /clan info <name>")
                return
            name = " ".join(args[1:])
            res = clan_info_by_name(name)
            await message.reply(res.message)
            return

        if sub == "bonus":
            res = clan_bonus(message.from_user.id, message.from_user.username)
            await message.reply(res.message)
            return

        await message.reply("❌ زیردستور نامعتبر. /clan را بدون آرگومان بزن.")
