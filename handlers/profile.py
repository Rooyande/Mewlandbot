from aiogram import types
from aiogram.dispatcher import Dispatcher

from db.repo_users import get_or_create_user, get_user_by_tg
from services.economy import MEW_COOLDOWN_SECONDS
from utils.time import now_ts, format_mm_ss


def register(dp: Dispatcher):
    @dp.message_handler(commands=["profile"])
    async def profile_cmd(message: types.Message):
        user_tg = message.from_user.id
        username = message.from_user.username

        get_or_create_user(user_tg, username)
        user = get_user_by_tg(user_tg)

        if not user:
            await message.reply("❌ خطا در بارگذاری پروفایل.")
            return

        points = int(user.get("mew_points") or 0)
        last_mew = int(user.get("last_mew_ts") or 0)
        now = now_ts()

        diff = now - last_mew
        if diff >= MEW_COOLDOWN_SECONDS:
            cd_text = "✅ آماده برای mew"
        else:
            cd_text = f"⏳ کول‌داون: {format_mm_ss(MEW_COOLDOWN_SECONDS - diff)}"

        await message.reply(
            f"👤 پروفایل\n"
            f"💰 امتیاز: {points}\n"
            f"{cd_text}"
        )
