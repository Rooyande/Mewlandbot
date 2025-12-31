from aiogram import types
from aiogram.dispatcher import Dispatcher

from db.repo_users import get_or_create_user, get_user_by_tg
from db.repo_cats import list_user_cats
from services.economy import MEW_COOLDOWN_SECONDS, apply_passive_income
from domain.constants import RARITY_CONFIG
from utils.time import now_ts, format_mm_ss


def _cat_mph(cat: dict) -> float:
    rarity = cat.get("rarity", "common")
    base = float(RARITY_CONFIG.get(rarity, RARITY_CONFIG["common"]).get("base_mph", 1.0))
    level = int(cat.get("level", 1))
    level_mult = 1.0 + (level - 1) * 0.1
    return base * level_mult


def register(dp: Dispatcher):
    @dp.message_handler(commands=["profile"])
    async def profile_cmd(message: types.Message):
        user_tg = message.from_user.id
        username = message.from_user.username

        user_db_id = get_or_create_user(user_tg, username)

        passive_gained = apply_passive_income(user_tg, user_db_id)

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

        cats = list_user_cats(user_db_id, include_dead=False)
        total_mph = 0.0
        for c in cats:
            total_mph += _cat_mph(c)

        text = (
            f"👤 پروفایل\n"
            f"💰 امتیاز: {points}\n"
            f"{cd_text}\n"
            f"🐱 تعداد گربه‌ها: {len(cats)}\n"
            f"⚡ درآمد ساعتی: {total_mph:.1f} میو/ساعت"
        )

        if passive_gained > 0:
            text += f"\n💤 در این بازدید: +{passive_gained} درآمد غیرفعال"

        await message.reply(text)
