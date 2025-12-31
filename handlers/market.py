from aiogram import types
from aiogram.dispatcher import Dispatcher

from services.market import (
    market_list,
    market_browse,
    market_my,
    market_buy,
    market_cancel,
)


def register(dp: Dispatcher):
    @dp.message_handler(commands=["market"])
    async def market_cmd(message: types.Message):
        args = (message.get_args() or "").split()
        if not args:
            await message.reply(
                "🏪 بازار\n\n"
                "دستورات:\n"
                "/market list <cat_id> <price>\n"
                "/market browse\n"
                "/market buy <listing_id>\n"
                "/market my\n"
                "/market cancel <listing_id>\n"
            )
            return

        sub = args[0].lower()

        if sub == "browse":
            await message.reply(market_browse())
            return

        if sub == "my":
            await message.reply(market_my(message.from_user.id, message.from_user.username))
            return

        if sub == "list":
            if len(args) != 3:
                await message.reply("❌ فرمت: /market list <cat_id> <price>")
                return
            try:
                cat_id = int(args[1])
                price = int(args[2])
            except ValueError:
                await message.reply("❌ cat_id و price باید عدد باشند.")
                return
            res = market_list(message.from_user.id, message.from_user.username, cat_id, price)
            await message.reply(res.message)
            return

        if sub == "buy":
            if len(args) != 2:
                await message.reply("❌ فرمت: /market buy <listing_id>")
                return
            try:
                listing_id = int(args[1])
            except ValueError:
                await message.reply("❌ listing_id باید عدد باشد.")
                return
            res = market_buy(message.from_user.id, message.from_user.username, listing_id)
            await message.reply(res.message)
            return

        if sub == "cancel":
            if len(args) != 2:
                await message.reply("❌ فرمت: /market cancel <listing_id>")
                return
            try:
                listing_id = int(args[1])
            except ValueError:
                await message.reply("❌ listing_id باید عدد باشد.")
                return
            res = market_cancel(message.from_user.id, message.from_user.username, listing_id)
            await message.reply(res.message)
            return

        await message.reply("❌ زیردستور نامعتبر. /market را بدون آرگومان بزن.")
