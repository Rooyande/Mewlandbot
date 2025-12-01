# bot.py

import logging
import os
import random
import time
from typing import Dict, Any

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Regexp
from aiogram.utils.exceptions import TelegramAPIError

from db import (
    init_db,
    get_user,
    get_or_create_user,
    update_user_mew,
    register_user_group,
    get_user_cats,
    add_cat,
    get_cat,
    update_cat_stats,
    rename_cat,
    set_cat_owner,
    get_leaderboard,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------- تنظیمات محیط ---------

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

ADMIN_ID = 8423995337  # آیدی تلگرام تو

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://mewlandbot.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

APP_HOST = "0.0.0.0"
APP_PORT = int(os.getenv("PORT", "10000"))

bot = Bot(BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# --------- کانفیگ گیم ---------

MEW_COOLDOWN = 7 * 60  # ۷ دقیقه
STARVE_SECONDS = 36 * 60 * 60  # ۳۶ ساعت
HUNGER_DECAY_PER_HOUR = 3      # هر ساعت ۳ واحد
HAPPINESS_DECAY_PER_HOUR = 2   # هر ساعت ۲ واحد

CAT_PRICES = {
    "common": 100,
    "rare": 150,
    "epic": 400,
    "legendary": 2000,
    "mythic": 2500,
}

RARITY_WEIGHTS = [
    ("common", 55),
    ("rare", 25),
    ("epic", 12),
    ("legendary", 6),
    ("mythic", 2),
]

ELEMENTS = ["fire", "water", "earth", "air", "shadow", "light"]
TRAITS = ["lazy", "hyper", "greedy", "cuddly", "brave", "shy"]

# گیف‌های نمایشی — بعداً لینک‌ها/فایل‌آی‌دی واقعی خودت رو بذار
PLAY_GIFS = [
    "https://media.giphy.com/media/JIX9t2j0ZTN9S/giphy.gif",
    "https://media.giphy.com/media/mlvseq9yvZhba/giphy.gif",
]
FEED_GIFS = [
    "https://media.giphy.com/media/12HZukMBlutpoQ/giphy.gif",
]
CUSTOM_GIFS = [
    "https://media.giphy.com/media/v6aOjy0Qo1fIA/giphy.gif",
]

# رویدادهای رندوم روزانه
RANDOM_EVENTS = [
    {
        "id": "homeless_cat",
        "text": "📢 رویداد روزانه:\nیک گربه‌ی بی‌خانمان دم گروه پرسه می‌زنه!\nاولین کسی که فقط با ایموجی 🏠 جواب بده، یک گربه‌ی Common می‌بره.",
        "answer": "🏠",
        "reward": {"type": "cat", "rarity": "common"},
    },
    {
        "id": "fish_rain",
        "text": "🐟 بارون ماهی شروع شد!\nاولین کسی که فقط با ایموجی 🐟 جواب بده ۳۰ میوپوینت می‌گیره.",
        "answer": "🐟",
        "reward": {"type": "points", "amount": 30},
    },
    {
        "id": "milk_shop",
        "text": "🥛 فروش ویژه‌ی شیر برای گربه‌ها!\nاولین کسی که فقط با ایموجی 🥛 جواب بده، ۴۰ میوپوینت برای خرید غذای گربه‌ها می‌گیره.",
        "answer": "🥛",
        "reward": {"type": "points", "amount": 40},
    },
    {
        "id": "toy_sale",
        "text": "🧶 حراج اسباب‌بازی گربه!\nاولین کسی که فقط با ایموجی 🧶 جواب بده، ۲۰ میوپوینت + ۱۰ happiness برای یکی از گربه‌هاش می‌گیره (گربه‌ی رندوم).",
        "answer": "🧶",
        "reward": {"type": "points_plus_happy", "points": 20, "happy": 10},
    },
    {
        "id": "stray_kitten",
        "text": "🐱 یک بچه‌گربه‌ی گمشده پیدا شده.\nاولین کسی که فقط با ایموجی ❤️ جواب بده، یک گربه‌ی Rare می‌گیره.",
        "answer": "❤️",
        "reward": {"type": "cat", "rarity": "rare"},
    },
    {
        "id": "night_watch",
        "text": "🌙 گربه‌ها شب‌بیدارن!\nاولین کسی که فقط با ایموجی 🌙 جواب بده، ۲۵ میوپوینت می‌گیره.",
        "answer": "🌙",
        "reward": {"type": "points", "amount": 25},
    },
    {
        "id": "mystery_box",
        "text": "🎁 جعبه‌ی مرموز گربه‌ای!\nاولین کسی که فقط با ایموجی 🎁 جواب بده، یک گربه‌ی Common یا Rare رندوم می‌گیره.",
        "answer": "🎁",
        "reward": {"type": "cat_random_common_rare"},
    },
    {
        "id": "clean_litter",
        "text": "🧹 جعبه‌شن گربه‌ها خیلی کثیف شده.\nاولین کسی که فقط با ایموجی 🧹 جواب بده، ۳۰ happiness برای یکی از گربه‌هاش می‌گیره.",
        "answer": "🧹",
        "reward": {"type": "happy_only", "happy": 30},
    },
    {
        "id": "vet_visit",
        "text": "⚕️ دکتر دامپزشک رایگان آمده.\nاولین کسی که فقط با ایموجی ⚕️ جواب بده، ۵۰ میوپوینت می‌گیره.",
        "answer": "⚕️",
        "reward": {"type": "points", "amount": 50},
    },
    {
        "id": "sun_spot",
        "text": "☀️ لکه‌ی آفتابی مورد علاقه‌ی گربه‌ها پیدا شد.\nاولین کسی که فقط با ایموجی ☀️ جواب بده، ۱۵ happiness برای همه‌ی گربه‌هاش می‌گیره (اگر داشته باشه).",
        "answer": "☀️",
        "reward": {"type": "happy_all", "happy": 15},
    },
]

# وضعیت رویدادهای فعال در هر گروه (فقط توی رم)
active_events: Dict[int, Dict[str, Any]] = {}
# برای اینکه روزی حداکثر ۲ رویداد بیاد
daily_event_counter: Dict[int, Dict[str, Any]] = {}


# --------- Helper های کلی ---------

async def notify_admin_error(msg: str):
    try:
        await bot.send_message(ADMIN_ID, f"⚠️ Error:\n<code>{msg}</code>")
    except TelegramAPIError:
        logger.exception("Failed to notify admin.")


def choose_rarity() -> str:
    roll = random.randint(1, 100)
    cur = 0
    for rarity, w in RARITY_WEIGHTS:
        cur += w
        if roll <= cur:
            return rarity
    return "common"


def rarity_emoji(rarity: str) -> str:
    return {
        "common": "⚪️",
        "rare": "🟦",
        "epic": "🟪",
        "legendary": "🟨",
        "mythic": "🟥",
    }.get(rarity, "⚪️")


def apply_cat_tick(cat: Dict[str, Any]) -> Dict[str, Any]:
    """
    کاهش گرسنگی و شادی بر اساس زمان، و چک مرگ ۳۶ ساعته.
    مرگ «مجازی» است؛ توی DB ستون اضافه نمی‌کنیم.
    """
    now = int(time.time())
    last = cat.get("last_tick_ts") or cat.get("created_at") or now
    elapsed = max(0, now - last)

    # اگر کمتر از ۱۰ دقیقه، ولش کن برای کاهش DB write
    if elapsed < 600:
        cat["virtual_dead"] = False
        return cat

    hours = elapsed / 3600.0

    hunger = int(cat.get("hunger", 60) - HUNGER_DECAY_PER_HOUR * hours)
    happiness = int(cat.get("happiness", 60) - HAPPINESS_DECAY_PER_HOUR * hours)

    hunger = max(hunger, 0)
    happiness = max(happiness, 0)

    virtual_dead = False
    if hunger == 0 and elapsed >= STARVE_SECONDS:
        virtual_dead = True

    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["last_tick_ts"] = now
    cat["virtual_dead"] = virtual_dead

    return cat


async def maybe_trigger_random_event(message: types.Message):
    """
    روزی حداکثر ۲ رویداد در هر گروه، با کمی شانس.
    روی هر پیام که بات درگیرش می‌شود چک می‌کنیم.
    """
    if message.chat.type not in ("group", "supergroup"):
        return

    chat_id = message.chat.id
    now = int(time.time())
    today = time.strftime("%Y-%m-%d", time.gmtime(now))

    info = daily_event_counter.get(chat_id)
    if info is None or info.get("date") != today:
        info = {"date": today, "count": 0, "last_ts": 0}
        daily_event_counter[chat_id] = info

    if info["count"] >= 2:
        return

    if now - info["last_ts"] < 3600:  # حداقل یک ساعت فاصله
        return

    # شانس ۱۵٪ برای تریگر
    if random.random() > 0.15:
        return

    event = random.choice(RANDOM_EVENTS)
    active_events[chat_id] = {
        "event": event,
        "ts": now,
    }

    info["count"] += 1
    info["last_ts"] = now

    await bot.send_message(chat_id, event["text"])


async def process_event_answer(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in active_events:
        return False

    evt_info = active_events[chat_id]
    event = evt_info["event"]
    answer = (message.text or "").strip()

    if answer != event["answer"]:
        return False

    # اولین جواب درست
    del active_events[chat_id]

    user_tg_id = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg_id, username)

    reward = event["reward"]
    desc_lines = []

    if reward["type"] == "points":
        u = get_user(user_tg_id)
        cur = (u.get("mew_points") or 0) if u else 0
        new_pts = cur + reward["amount"]
        update_user_mew(user_tg_id, mew_points=new_pts)
        desc_lines.append(f"🎉 {reward['amount']} میوپوینت گرفتی! الان {new_pts} امتیاز داری.")

    elif reward["type"] == "cat":
        rarity = reward["rarity"]
        element = random.choice(ELEMENTS)
        trait = random.choice(TRAITS)
        name = f"{rarity.title()} Cat"
        description = f"یک گربه‌ی {rarity} با عنصر {element} و اخلاق {trait}."
        cat_id = add_cat(user_db_id, name, rarity, element, trait, description)
        desc_lines.append(
            f"🎉 یک گربه‌ی جدید {rarity_emoji(rarity)} ({rarity}) گرفتی!\n"
            f"ID گربه: {cat_id}"
        )

    elif reward["type"] == "cat_random_common_rare":
        rarity = random.choice(["common", "rare"])
        element = random.choice(ELEMENTS)
        trait = random.choice(TRAITS)
        name = f"{rarity.title()} Cat"
        description = f"یک گربه‌ی {rarity} با عنصر {element} و اخلاق {trait}."
        cat_id = add_cat(user_db_id, name, rarity, element, trait, description)
        desc_lines.append(
            f"🎉 یک گربه‌ی {rarity_emoji(rarity)} ({rarity}) از جعبه مرموز گرفتی!\n"
            f"ID گربه: {cat_id}"
        )

    elif reward["type"] == "points_plus_happy":
        # امتیاز + شادی گربه‌ی رندوم
        u = get_user(user_tg_id)
        cur = (u.get("mew_points") or 0) if u else 0
        new_pts = cur + reward["points"]
        update_user_mew(user_tg_id, mew_points=new_pts)

        cats = get_user_cats(user_db_id)
        if cats:
            cat = random.choice(cats)
            cat = apply_cat_tick(cat)
            if not cat.get("virtual_dead"):
                new_happy = min(100, cat.get("happiness", 60) + reward["happy"])
                update_cat_stats(
                    cat_id=cat["id"],
                    owner_id=user_db_id,
                    happiness=new_happy,
                    last_tick_ts=cat["last_tick_ts"],
                )
                desc_lines.append(
                    f"🎉 {reward['points']} میوپوینت + {reward['happy']} شادی برای گربه‌ی {cat['name']} گرفتی!"
                )
            else:
                desc_lines.append(
                    f"🎉 {reward['points']} میوپوینت گرفتی؛ ولی گربه‌ای زنده نبود که شادی بگیرد 😿"
                )
        else:
            desc_lines.append(
                f"🎉 {reward['points']} میوپوینت گرفتی، ولی گربه‌ای نداری که شادی بگیرد."
            )

    elif reward["type"] == "happy_only":
        cats = get_user_cats(user_db_id)
        if cats:
            cat = random.choice(cats)
            cat = apply_cat_tick(cat)
            if not cat.get("virtual_dead"):
                new_happy = min(100, cat.get("happiness", 60) + reward["happy"])
                update_cat_stats(
                    cat_id=cat["id"],
                    owner_id=user_db_id,
                    happiness=new_happy,
                    last_tick_ts=cat["last_tick_ts"],
                )
                desc_lines.append(
                    f"🎉 {reward['happy']} شادی برای گربه‌ی {cat['name']} گرفتی!"
                )
            else:
                desc_lines.append("😿 همه‌ی گربه‌هات از گرسنگی مُرده‌اند...")
        else:
            desc_lines.append("😿 گربه‌ای نداری که شادی بگیرد.")

    elif reward["type"] == "happy_all":
        cats = get_user_cats(user_db_id)
        if cats:
            alive_count = 0
            for cat in cats:
                cat = apply_cat_tick(cat)
                if cat.get("virtual_dead"):
                    continue
                new_happy = min(100, cat.get("happiness", 60) + reward["happy"])
                update_cat_stats(
                    cat_id=cat["id"],
                    owner_id=user_db_id,
                    happiness=new_happy,
                    last_tick_ts=cat["last_tick_ts"],
                )
                alive_count += 1
            if alive_count:
                desc_lines.append(
                    f"🎉 {reward['happy']} شادی برای {alive_count} تا از گربه‌هات اضافه شد!"
                )
            else:
                desc_lines.append("😿 همه‌ی گربه‌هات از گرسنگی مُرده‌اند...")
        else:
            desc_lines.append("😿 گربه‌ای نداری.")

    if not desc_lines:
        desc_lines.append("🎉 جایزه‌ات اعمال شد.")

    await bot.send_message(
        message.chat.id,
        f"برنده رویداد: {message.from_user.full_name}\n" + "\n".join(desc_lines),
    )
    return True


# --------- دستورات اصلی ---------

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await maybe_trigger_random_event(message)

    get_or_create_user(message.from_user.id, message.from_user.username)

    text = (
        "سلام، من گربه‌باتِ میولندم 😼\n\n"
        "با نوشتن <b>mew</b> امتیاز می‌گیری، با امتیازها گربه می‌خری، "
        "غذا می‌دی، بازی می‌کنی و از گربه‌هات مراقبت می‌کنی.\n\n"
        "برای لیست دستورات: /help"
    )
    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await maybe_trigger_random_event(message)

    text = (
        "📜 لیست دستورات:\n\n"
        "mew — میو بزن و بین ۱ تا ۵ امتیاز بگیر (هر ۷ دقیقه یک‌بار)\n"
        "/profile — پروفایل و امتیازها و تعداد گربه‌ها\n"
        "/leaderboard — لیدربورد امتیاز میو\n"
        "/adopt — خرید یک گربه‌ی جدید (هزینه بر اساس rarity)\n"
        "/cats — لیست گربه‌های تو\n"
        "/feed <cat_id> <amount> — غذا دادن به گربه\n"
        "/play <cat_id> — بازی کردن با گربه\n"
        "/rename <cat_id> <name> — عوض کردن اسم گربه\n"
        "/transfer <cat_id> @user — انتقال گربه به شخص دیگر\n"
        "/customcat <cat_id> <ظاهر> — اضافه کردن ظاهر/اسکین به گربه\n"
    )
    await bot.send_message(message.chat.id, text)


# mew — رندم ۱ تا ۵ امتیاز
@dp.message_handler(Regexp(r"^(?i)mew$"))
async def handle_mew(message: types.Message):
    await maybe_trigger_random_event(message)

    user_tg = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id

    user_db_id = get_or_create_user(user_tg, username)
    register_user_group(user_db_id, chat_id)

    u = get_user(user_tg)
    now = int(time.time())

    last_mew = u.get("last_mew_ts") or 0
    diff = now - last_mew
    if diff < MEW_COOLDOWN:
        remaining = MEW_COOLDOWN - diff
        mins = remaining // 60
        secs = remaining % 60
        await bot.send_message(
            chat_id,
            f"هنوز باید {mins} دقیقه و {secs} ثانیه صبر کنی تا دوباره میو بزنی 😼",
        )
        return

    gained = random.randint(1, 5)
    cur_points = u.get("mew_points") or 0
    new_points = cur_points + gained

    update_user_mew(user_tg, mew_points=new_points, last_mew_ts=now)

    await bot.send_message(
        chat_id,
        f"مِیو! 😺\n"
        f"این بار <b>{gained}</b> امتیاز گرفتی و الان <b>{new_points}</b> میوپوینت داری.",
    )


@dp.message_handler(commands=["profile"])
async def cmd_profile(message: types.Message):
    await maybe_trigger_random_event(message)

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    u = get_user(user_tg)
    cats = get_user_cats(user_db_id)

    mew_points = (u.get("mew_points") or 0) if u else 0
    cat_count = len(cats) if cats else 0

    text = (
        f"🐾 پروفایل {message.from_user.full_name}\n\n"
        f"امتیاز میو: <b>{mew_points}</b>\n"
        f"تعداد گربه‌ها: <b>{cat_count}</b>\n"
    )
    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=["leaderboard"])
async def cmd_leaderboard(message: types.Message):
    await maybe_trigger_random_event(message)

    rows = get_leaderboard(limit=10)
    if not rows:
        await bot.send_message(message.chat.id, "هنوز کسی میو نزده 😿")
        return

    lines = ["🏆 لیدربورد میولند:\n"]
    for i, row in enumerate(rows, start=1):
        uname = row.get("username") or f"id:{row['telegram_id']}"
        pts = row.get("mew_points") or 0
        lines.append(f"{i}. {uname} — {pts} امتیاز")

    await bot.send_message(message.chat.id, "\n".join(lines))


@dp.message_handler(commands=["adopt"])
async def cmd_adopt(message: types.Message):
    await maybe_trigger_random_event(message)

    user_tg = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id

    user_db_id = get_or_create_user(user_tg, username)
    u = get_user(user_tg)
    mew_points = (u.get("mew_points") or 0) if u else 0

    rarity = choose_rarity()
    cost = CAT_PRICES.get(rarity, 100)

    if mew_points < cost:
        await bot.send_message(
            chat_id,
            f"برای گربه‌ی {rarity_emoji(rarity)} ({rarity}) حداقل {cost} امتیاز لازم داری.\n"
            f"الان فقط {mew_points} میوپوینت داری.",
        )
        return

    element = random.choice(ELEMENTS)
    trait = random.choice(TRAITS)
    name = f"{rarity.title()} Cat"
    description = f"یک گربه‌ی {rarity} با عنصر {element} و اخلاق {trait}."

    cat_id = add_cat(user_db_id, name, rarity, element, trait, description)
    update_user_mew(user_tg, mew_points=mew_points - cost)

    await bot.send_message(
        chat_id,
        f"🎉 یک گربه‌ی جدید گرفتن!\n\n"
        f"{rarity_emoji(rarity)} <b>{name}</b> ({rarity})\n"
        f"عنصر: {element}\n"
        f"خلق‌وخو: {trait}\n"
        f"ID گربه: <b>{cat_id}</b>\n\n"
        f"{cost} امتیاز خرج شد؛ الان {mew_points - cost} میوپوینت داری.",
    )


@dp.message_handler(commands=["cats"])
async def cmd_cats(message: types.Message):
    await maybe_trigger_random_event(message)

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    cats = get_user_cats(user_db_id)
    if not cats:
        await bot.send_message(message.chat.id, "هنوز هیچ گربه‌ای نداری 😿\nبا /adopt یکی بخر.")
        return

    lines = ["🐱 لیست گربه‌های تو:\n"]
    for cat in cats:
        cat = apply_cat_tick(cat)

        if cat.get("virtual_dead"):
            status = "☠️ مرده (۳۶ ساعت گرسنه بوده)"
        elif cat["hunger"] == 0:
            status = "⚠️ گرسنه تا حد مرگ"
        else:
            status = "زنده"

        lines.append(
            f"ID: {cat['id']} — {rarity_emoji(cat['rarity'])} {cat['name']} ({cat['rarity']})\n"
            f"🍗 گرسنگی: {cat['hunger']}/100\n"
            f"😊 خوشحالی: {cat['happiness']}/100\n"
            f"⬆️ لول: {cat['level']} (XP: {cat['xp']})\n"
            f"وضعیت: {status}\n"
            f"توضیحات: {cat['description']}\n"
            "-------------------------"
        )

        # ذخیره تغییرات گرسنگی/خوشحالی در DB (یکبار در لیست)
        if not cat.get("virtual_dead"):
            update_cat_stats(
                cat_id=cat["id"],
                owner_id=user_db_id,
                hunger=cat["hunger"],
                happiness=cat["happiness"],
                last_tick_ts=cat["last_tick_ts"],
            )

    await bot.send_message(message.chat.id, "\n".join(lines))


@dp.message_handler(commands=["feed"])
async def cmd_feed(message: types.Message):
    await maybe_trigger_random_event(message)

    parts = (message.get_args() or "").split()
    if len(parts) != 2:
        await bot.send_message(message.chat.id, "استفاده: /feed cat_id amount")
        return

    try:
        cat_id = int(parts[0])
        amount = int(parts[1])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id و amount باید عدد باشند.")
        return

    if amount <= 0:
        await bot.send_message(message.chat.id, "مقدار غذا باید مثبت باشد.")
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    cat = apply_cat_tick(cat)
    if cat.get("virtual_dead"):
        await bot.send_message(message.chat.id, "این گربه از گرسنگی مُرده 😿 دیگه نمی‌تونی بهش غذا بدی.")
        return

    hunger_before = cat["hunger"]
    hunger_after = hunger_before + amount

    # اوورفید: اگر خیلی بزنی
    msg = ""
    if hunger_after > 130:
        # گربه می‌میره از پرخوری
        hunger_after = 0
        happy_after = 0
        msg = "از پرخوری ترکید 😿 (دفعه بعد این‌قدر نریز براش...)"
    else:
        # مقاومت در بیش از ۱۱۰
        if hunger_after > 110:
            hunger_after = 100
            msg = "گربه خیلی سیر شد و بیشتر نمی‌خوره 😼"
        else:
            if hunger_after > 100:
                hunger_after = 100
                msg = "گربه شکمش تا خرخره پر شد، بیشتر جا نداره 😺"
            else:
                msg = "گربه با اشتها غذاشو خورد 😺"

        happy_after = min(100, cat["happiness"] + amount // 2)

    update_cat_stats(
        cat_id=cat["id"],
        owner_id=user_db_id,
        hunger=hunger_after,
        happiness=happy_after,
        last_tick_ts=int(time.time()),
    )

    # گیف تغذیه
    if FEED_GIFS:
        await bot.send_animation(message.chat.id, random.choice(FEED_GIFS))

    await bot.send_message(
        message.chat.id,
        f"{msg}\n\n"
        f"🍗 گرسنگی گربه از {hunger_before} به {hunger_after} رسید.\n"
        f"😊 خوشحالی الان {happy_after} است.",
    )


@dp.message_handler(commands=["play"])
async def cmd_play(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split()
    if len(args) != 1:
        await bot.send_message(message.chat.id, "استفاده: /play cat_id")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id باید عدد باشد.")
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    cat = apply_cat_tick(cat)
    if cat.get("virtual_dead"):
        await bot.send_message(message.chat.id, "این گربه از گرسنگی مُرده، دیگه بازی نمی‌کنه 😿")
        return

    happy_before = cat["happiness"]
    hunger_before = cat["hunger"]

    happy_after = min(100, happy_before + 15)
    hunger_after = max(0, hunger_before - 5)
    xp_after = cat["xp"] + 10
    level_after = cat["level"]
    if xp_after >= 100:
        level_after += 1
        xp_after -= 100

    update_cat_stats(
        cat_id=cat["id"],
        owner_id=user_db_id,
        happiness=happy_after,
        hunger=hunger_after,
        xp=xp_after,
        level=level_after,
        last_tick_ts=int(time.time()),
    )

    if PLAY_GIFS:
        await bot.send_animation(message.chat.id, random.choice(PLAY_GIFS))

    text = (
        f"با گربه‌ی <b>{cat['name']}</b> بازی کردی 😺\n\n"
        f"😊 خوشحالی: {happy_before} ➜ {happy_after}\n"
        f"🍗 گرسنگی: {hunger_before} ➜ {hunger_after}\n"
        f"⬆️ لول: {cat['level']} ➜ {level_after} (XP: {xp_after})"
    )
    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=["rename"])
async def cmd_rename(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split(maxsplit=1)
    if len(args) != 2:
        await bot.send_message(message.chat.id, "استفاده: /rename cat_id name")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id باید عدد باشد.")
        return

    new_name = args[1].strip()
    if not new_name:
        await bot.send_message(message.chat.id, "اسم نمی‌تونه خالی باشه.")
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    rename_cat(user_db_id, cat_id, new_name)
    await bot.send_message(
        message.chat.id,
        f"اسم گربه از <b>{cat['name']}</b> به <b>{new_name}</b> تغییر کرد 😺",
    )


@dp.message_handler(commands=["transfer"])
async def cmd_transfer(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split()
    if len(args) != 2:
        await bot.send_message(message.chat.id, "استفاده: /transfer cat_id @username")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id باید عدد باشد.")
        return

    target_username = args[1].lstrip("@").strip()
    if not target_username:
        await bot.send_message(message.chat.id, "یوزرنیم هدف درست نیست.")
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    from_db_id = get_or_create_user(user_tg, username)

    cat = get_cat(cat_id, owner_id=from_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    # متأسفانه از روی @username نمی‌تونیم telegram_id رو ۱۰۰٪ بفهمیم.
    # برای نسخه‌ی ساده: فقط اگر طرف قبلاً با بات کار کرده باشد و توی DB باشد.
    all_users = get_all_users()
    target_row = None
    for u in all_users:
        if (u.get("username") or "").lower() == target_username.lower():
            target_row = u
            break

    if not target_row:
        await bot.send_message(
            message.chat.id,
            "کاربر هدف هنوز با بات کار نکرده یا توی دیتابیس نیست. "
            "بگو یک /start به بات بده بعد دوباره /transfer رو بزن.",
        )
        return

    to_db_id = target_row["id"]
    set_cat_owner(cat_id, to_db_id)

    await bot.send_message(
        message.chat.id,
        f"گربه‌ی <b>{cat['name']}</b> با ID {cat_id} منتقل شد به @{target_username} 😼",
    )


@dp.message_handler(commands=["customcat"])
async def cmd_customcat(message: types.Message):
    """
    ظاهر/اسکین ساده: متن ظاهری رو به description اضافه می‌کنیم.
    ستون جدید لازم نداره.
    """
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split(maxsplit=1)
    if len(args) != 2:
        await bot.send_message(message.chat.id, "استفاده: /customcat cat_id ظاهر")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id باید عدد باشد.")
        return

    appearance = args[1].strip()
    if not appearance:
        await bot.send_message(message.chat.id, "ظاهر نمی‌تونه خالی باشه.")
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    base_desc = cat.get("description") or ""
    new_desc = base_desc + f" | ظاهر: {appearance}"

    update_cat_stats(
        cat_id=cat_id,
        owner_id=user_db_id,
        description=new_desc,
    )

    if CUSTOM_GIFS:
        await bot.send_animation(message.chat.id, random.choice(CUSTOM_GIFS))

    await bot.send_message(
        message.chat.id,
        f"ظاهر گربه‌ی <b>{cat['name']}</b> به شکل «{appearance}» تنظیم شد 😺",
    )


# --------- هندلر رویدادهای رندوم (جواب دادن) ---------

@dp.message_handler()
async def catch_all(message: types.Message):
    # اول رویدادهای رندوم
    handled = await process_event_answer(message)
    if handled:
        return
    # اگر چیز دیگه‌ای بود که بهش نرسیدیم، همینجا می‌تونیم بعداً اضافه کنیم.
    return


# --------- وب‌سرور برای وبهوک ---------

async def handle_root(request: web.Request):
    return web.Response(text="Mewland bot is running.")


async def handle_webhook(request: web.Request):
    token = request.match_info.get("token")
    if token != BOT_TOKEN:
        return web.Response(status=403)

    data = await request.json()
    update = types.Update(**data)

    try:
        await dp.process_update(update)
    except Exception as e:
        logger.exception("Unhandled error: %s", e)
        await notify_admin_error(str(e))

    return web.Response(status=200)


async def on_startup(app: web.Application):
    logger.info("Deleting old webhook (if any)...")
    try:
        await bot.delete_webhook()
    except TelegramAPIError:
        pass

    logger.info("Setting webhook to %s", WEBHOOK_URL)
    await bot.set_webhook(WEBHOOK_URL)

    init_db()
    logger.info("Startup finished.")


def main():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_post("/webhook/{token}", handle_webhook)
    app.on_startup.append(on_startup)

    web.run_app(app, host=APP_HOST, port=APP_PORT)


if __name__ == "__main__":
    main()
