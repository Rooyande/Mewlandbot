from aiogram import types
from aiogram.dispatcher import Dispatcher

from services.economy import mew_action
from utils.time import format_mm_ss


def register(dp: Dispatcher):
    @dp.message_handler(lambda m: m.text and m.text.strip().lower() == "mew")
    async def mew_text(message: types.Message):
        user_tg = message.from_user.id
        username = message.from_user.username

        res = mew_action(user_tg, username)

        if not res.ok:
            text = f"⏳ باید {format_mm_ss(res.cooldown_left)} صبر کنی.\n💰 امتیاز فعلی: {res.total}"
            if res.passive_gained > 0:
                text += f"\n💤 +{res.passive_gained} درآمد غیرفعال"
            await message.reply(text)
            return

        text = f"😺 میو!\n🎁 {res.gained} امتیاز گرفتی."
        if res.passive_gained > 0:
            text += f"\n💤 +{res.passive_gained} درآمد غیرفعال"
        text += f"\n💰 مجموع: {res.total}"
        await message.reply(text)
