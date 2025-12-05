# bot.py

import logging
import os
import random
import time
from typing import Dict, Any, List

from aiohttp import web
from aiogram import Bot, Dispatcher, types
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
    get_all_users,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========= ENV / TELEGRAM / WEBHOOK =========

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

ADMIN_ID = 8423995337  # your Telegram ID

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://mewlandbot.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

APP_HOST = "0.0.0.0"
APP_PORT = int(os.getenv("PORT", "10000"))

bot = Bot(BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# ========= GAME CONFIG =========

MEW_COOLDOWN = 7 * 60       # 7 minutes
PASSIVE_MIN_INTERVAL = 15 * 60  # only recalc passive income every 15 minutes

# hunger / happiness decay
HUNGER_DECAY_PER_HOUR = 5
HAPPINESS_DECAY_PER_HOUR = 3

# rarity config: price & base meow/hour
RARITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "common":    {"price": 200,   "base_mph": 1.0},
    "rare":      {"price": 800,   "base_mph": 3.0},
    "epic":      {"price": 2500,  "base_mph": 7.0},
    "legendary": {"price": 7000,  "base_mph": 15.0},
    "mythic":    {"price": 15000, "base_mph": 30.0},
}

RARITY_WEIGHTS = [
    ("common", 55),
    ("rare", 25),
    ("epic", 12),
    ("legendary", 6),
    ("mythic", 2),
]

PERSONALITIES = ["chill", "chaotic", "tsundere", "clingy", "royal", "gremlin"]
ELEMENTS = ["fire", "water", "earth", "air", "shadow", "light"]
TRAITS = ["lazy", "hyper", "greedy", "cuddly", "brave", "shy", "noisy", "sleepy"]

# base XP to level up (simple: every 100 xp = +1 level)
XP_PER_LEVEL = 100

# gear shop: item_code -> stats
GEAR_ITEMS: Dict[str, Dict[str, Any]] = {
    "scarf": {
        "name": "🧣 شال گرم",
        "price": 500,
        "mph_bonus": 2.0,
        "power_bonus": 1,
        "agility_bonus": 0,
        "luck_bonus": 0,
    },
    "bell": {
        "name": "🔔 گردنبند زنگوله‌ای",
        "price": 800,
        "mph_bonus": 3.0,
        "power_bonus": 0,
        "agility_bonus": 1,
        "luck_bonus": 1,
    },
    "boots": {
        "name": "🥾 چکمه تریپ‌دار",
        "price": 1200,
        "mph_bonus": 1.0,
        "power_bonus": 0,
        "agility_bonus": 3,
        "luck_bonus": 0,
    },
    "crown": {
        "name": "👑 تاج سلطنتی",
        "price": 3000,
        "mph_bonus": 5.0,
        "power_bonus": 2,
        "agility_bonus": 1,
        "luck_bonus": 2,
    },
}

# gifs (you can replace with Telegram file_ids later)
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

# random emoji events (3 per day per group)
RANDOM_EVENTS = [
    {
        "id": "homeless_cat",
        "text": "📢 رویداد روزانه:\nیک گربه‌ی بی‌خانمان دم گروه پرسه می‌زنه!\nاولین کسی که فقط با ایموجی 🏠 جواب بده، یک گربه‌ی Common می‌بره.",
        "answer": "🏠",
        "reward": {"type": "cat", "rarity": "common"},
    },
    {
        "id": "fish_rain",
        "text": "🐟 بارون ماهیِ معجزه‌ای!\nاولین کسی که فقط با ایموجی 🐟 جواب بده ۳۰ میوپوینت می‌گیره.",
        "answer": "🐟",
        "reward": {"type": "points", "amount": 30},
    },
    {
        "id": "milk_shop",
        "text": "🥛 فروش ویژه شیر برای گربه‌ها!\nاولین کسی که فقط با ایموجی 🥛 جواب بده، ۴۰ میوپوینت می‌گیره.",
        "answer": "🥛",
        "reward": {"type": "points", "amount": 40},
    },
    {
        "id": "toy_sale",
        "text": "🧶 حراج اسباب‌بازی گربه!\nاولین کسی که فقط با ایموجی 🧶 جواب بده، ۲۰ میوپوینت + ۱۰ خوشحالی برای یک گربه‌اش می‌گیره.",
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
        "text": "🌙 گربه‌ها شب‌گردی دارن!\nاولین کسی که فقط با ایموجی 🌙 جواب بده، ۲۵ میوپوینت می‌گیره.",
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
        "text": "🧹 جعبه‌شن گربه‌ها بو گرفته.\nاولین کسی که فقط با ایموجی 🧹 جواب بده، ۳۰ خوشحالی برای یک گربه‌اش می‌گیره.",
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
        "text": "☀️ لکه‌ی آفتابی مورد علاقه‌ی گربه‌ها پیدا شد.\nاولین کسی که فقط با ایموجی ☀️ جواب بده، ۱۵ خوشحالی برای همه‌ی گربه‌هاش می‌گیره.",
        "answer": "☀️",
        "reward": {"type": "happy_all", "happy": 15},
    },
]

# in-memory per-process state
active_events: Dict[int, Dict[str, Any]] = {}
daily_event_counter: Dict[int, Dict[str, Any]] = {}  # chat_id -> {date, count, last_ts}


# ========= helper functions =========

async def notify_admin_error(msg: str):
    try:
        safe = msg.replace("&", "&amp;").replace("<", "&lt;")
        await bot.send_message(ADMIN_ID, f"⚠️ Error:\n<code>{safe}</code>")
    except TelegramAPIError:
        logger.exception("Failed to notify admin.")


def rarity_emoji(rarity: str) -> str:
    return {
        "common": "⚪️",
        "rare": "🟦",
        "epic": "🟪",
        "legendary": "🟨",
        "mythic": "🟥",
    }.get(rarity, "⚪️")


def choose_rarity() -> str:
    roll = random.randint(1, 100)
    cur = 0
    for rarity, w in RARITY_WEIGHTS:
        cur += w
        if roll <= cur:
            return rarity
    return "common"


def parse_gear_codes(gear_field: Any) -> List[str]:
    if not gear_field:
        return []
    if isinstance(gear_field, list):
        # in case someday it's stored as array
        return [str(x) for x in gear_field]
    s = str(gear_field)
    return [g.strip() for g in s.split(",") if g.strip()]


def compute_cat_effective_stats(cat: Dict[str, Any]) -> Dict[str, Any]:
    power = int(cat.get("stat_power", 1))
    agility = int(cat.get("stat_agility", 1))
    luck = int(cat.get("stat_luck", 1))

    gear_codes = parse_gear_codes(cat.get("gear"))
    for code in gear_codes:
        item = GEAR_ITEMS.get(code)
        if not item:
            continue
        power += int(item.get("power_bonus", 0))
        agility += int(item.get("agility_bonus", 0))
        luck += int(item.get("luck_bonus", 0))

    return {"power": power, "agility": agility, "luck": luck}


def compute_cat_mph(cat: Dict[str, Any]) -> float:
    rarity = cat.get("rarity", "common")
    conf = RARITY_CONFIG.get(rarity, RARITY_CONFIG["common"])
    base = float(conf["base_mph"])
    level = int(cat.get("level", 1))
    level_mult = 1.0 + 0.05 * max(0, level - 1)

    gear_codes = parse_gear_codes(cat.get("gear"))
    gear_bonus = 0.0
    for code in gear_codes:
        item = GEAR_ITEMS.get(code)
        if item:
            gear_bonus += float(item.get("mph_bonus", 0.0))

    return base * level_mult + gear_bonus


def apply_cat_tick(cat: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply hunger & happiness decay based on elapsed time.
    We do NOT write to DB here; caller decides when to persist.
    """
    now = int(time.time())
    last = cat.get("last_tick_ts") or cat.get("created_at") or now
    elapsed = max(0, now - int(last))

    if elapsed < 300:  # less than 5 minutes, ignore to reduce noise
        cat["last_tick_ts"] = last
        return cat

    hours = elapsed / 3600.0

    hunger = int(cat.get("hunger", 80) - HUNGER_DECAY_PER_HOUR * hours)
    happiness = int(cat.get("happiness", 80) - HAPPINESS_DECAY_PER_HOUR * hours)

    hunger = max(hunger, 0)
    happiness = max(happiness, 0)

    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["last_tick_ts"] = now
    return cat


def apply_passive_income(telegram_id: int, user_db_id: int) -> int:
    """
    Calculate meow/hour passive from all cats and credit user.
    Returns how many points were added this time.
    """
    u = get_user(telegram_id)
    if not u:
        return 0

    now = int(time.time())
    last_passive = u.get("last_passive_ts") or u.get("created_at") or now
    elapsed = max(0, now - int(last_passive))

    if elapsed < PASSIVE_MIN_INTERVAL:
        return 0

    hours = elapsed / 3600.0

    cats = get_user_cats(user_db_id)
    total_mph = 0.0
    for cat in cats:
        total_mph += compute_cat_mph(cat)

    gained = int(total_mph * hours)
    new_points = int(u.get("mew_points") or 0)
    if gained > 0:
        new_points += gained
        update_user_mew(
            telegram_id,
            mew_points=new_points,
            last_passive_ts=now,
        )
    else:
        update_user_mew(
            telegram_id,
            last_passive_ts=now,
        )

    return gained


async def maybe_trigger_random_event(message: types.Message):
    """
    Up to 3 events per day per group, with a bit of randomness.
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

    if info["count"] >= 3:
        return

    if now - info["last_ts"] < 3600:  # at least 1 hour between events
        return

    if random.random() > 0.18:  # ~18% chance
        return

    event = random.choice(RANDOM_EVENTS)
    active_events[chat_id] = {
        "event": event,
        "ts": now,
    }

    info["count"] += 1
    info["last_ts"] = now

    await bot.send_message(chat_id, event["text"])


async def process_event_answer(message: types.Message) -> bool:
    chat_id = message.chat.id
    if chat_id not in active_events:
        return False

    evt_info = active_events[chat_id]
    event = evt_info["event"]
    answer = (message.text or "").strip()

    if answer != event["answer"]:
        return False

    # first correct answer wins
    del active_events[chat_id]

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    reward = event["reward"]
    desc_lines = []

    if reward["type"] == "points":
        u = get_user(user_tg)
        cur = (u.get("mew_points") or 0) if u else 0
        new_pts = cur + reward["amount"]
        update_user_mew(user_tg, mew_points=new_pts)
        desc_lines.append(f"🎉 {reward['amount']} میوپوینت گرفتی! الان {new_pts} امتیاز داری.")

    elif reward["type"] == "cat":
        rarity = reward["rarity"]
        personality = random.choice(PERSONALITIES)
        element = random.choice(ELEMENTS)
        trait = random.choice(TRAITS)
        name = f"{rarity.title()} Cat"
        description = f"یک گربه‌ی {rarity} با شخصیت {personality}، عنصر {element} و خوی {trait}."
        cat_id = add_cat(user_db_id, name, rarity, personality, element, trait, description)
        desc_lines.append(
            f"🎉 یک گربه‌ی جدید {rarity_emoji(rarity)} ({rarity}) گرفتی!\n"
            f"ID گربه: {cat_id}"
        )

    elif reward["type"] == "cat_random_common_rare":
        rarity = random.choice(["common", "rare"])
        personality = random.choice(PERSONALITIES)
        element = random.choice(ELEMENTS)
        trait = random.choice(TRAITS)
        name = f"{rarity.title()} Cat"
        description = f"یک گربه‌ی {rarity} با شخصیت {personality}، عنصر {element} و خوی {trait}."
        cat_id = add_cat(user_db_id, name, rarity, personality, element, trait, description)
        desc_lines.append(
            f"🎉 یک گربه‌ی {rarity_emoji(rarity)} ({rarity}) از جعبه مرموز گرفتی!\n"
            f"ID گربه: {cat_id}"
        )

    elif reward["type"] == "points_plus_happy":
        u = get_user(user_tg)
        cur = (u.get("mew_points") or 0) if u else 0
        new_pts = cur + reward["points"]
        update_user_mew(user_tg, mew_points=new_pts)

        cats = get_user_cats(user_db_id)
        if cats:
            cat = random.choice(cats)
            cat = apply_cat_tick(cat)
            new_happy = min(100, cat.get("happiness", 80) + reward["happy"])
            update_cat_stats(
                cat_id=cat["id"],
                owner_id=user_db_id,
                happiness=new_happy,
                last_tick_ts=cat["last_tick_ts"],
            )
            desc_lines.append(
                f"🎉 {reward['points']} میوپوینت + {reward['happy']} خوشحالی برای گربه‌ی {cat['name']} گرفتی!"
            )
        else:
            desc_lines.append(
                f"🎉 {reward['points']} میوپوینت گرفتی، ولی هنوز گربه‌ای نداری."
            )

    elif reward["type"] == "happy_only":
        cats = get_user_cats(user_db_id)
        if cats:
            cat = random.choice(cats)
            cat = apply_cat_tick(cat)
            new_happy = min(100, cat.get("happiness", 80) + reward["happy"])
            update_cat_stats(
                cat_id=cat["id"],
                owner_id=user_db_id,
                happiness=new_happy,
                last_tick_ts=cat["last_tick_ts"],
            )
            desc_lines.append(
                f"🎉 {reward['happy']} خوشحالی برای گربه‌ی {cat['name']} گرفتی!"
            )
        else:
            desc_lines.append("😿 گربه‌ای نداری که خوشحال بشه.")

    elif reward["type"] == "happy_all":
        cats = get_user_cats(user_db_id)
        if cats:
            alive_count = 0
            for cat in cats:
                cat = apply_cat_tick(cat)
                new_happy = min(100, cat.get("happiness", 80) + reward["happy"])
                update_cat_stats(
                    cat_id=cat["id"],
                    owner_id=user_db_id,
                    happiness=new_happy,
                    last_tick_ts=cat["last_tick_ts"],
                )
                alive_count += 1
            desc_lines.append(
                f"🎉 {reward['happy']} خوشحالی برای {alive_count} تا از گربه‌هات اضافه شد!"
            )
        else:
            desc_lines.append("😿 هنوز گربه‌ای نداری.")

    if not desc_lines:
        desc_lines.append("🎉 جایزه‌ات اعمال شد.")

    await bot.send_message(
        message.chat.id,
        f"برنده‌ی رویداد: {message.from_user.full_name}\n" + "\n".join(desc_lines),
    )
    return True


# ========= COMMAND HANDLERS =========

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await maybe_trigger_random_event(message)

    get_or_create_user(message.from_user.id, message.from_user.username)

    text = (
        "سلام، من گربه‌بات میولندم 😼\n\n"
        "با نوشتن <b>mew</b> امتیاز می‌گیری، با امتیازها گربه می‌خری، "
        "غذا می‌دی، بازی می‌کنی، تجهیزات می‌خری و حتی گربه‌ها رو به جون هم می‌اندازی.\n\n"
        "برای لیست دستورات: /help"
    )
    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await maybe_trigger_random_event(message)

    text = (
        "📜 لیست دستورات میولند:\n\n"
        "mew — میو بزن و بین ۱ تا ۵ امتیاز بگیر (هر ۷ دقیقه یک‌بار)\n"
        "/profile — پروفایل، امتیازها و خلاصه وضعیت گربه‌ها\n"
        "/leaderboard — جدول برترین‌ها\n"
        "/adopt — خرید یک گربه‌ی رندوم (بر اساس rarity)\n"
        "/adopt rarity — خرید گربه با rarity مشخص (مثال: /adopt rare)\n"
        "/cats — لیست تمام گربه‌ها و وضعیت‌شون\n"
        "/feed cat_id amount — غذا دادن به گربه (هزینه امتیاز، افزایش گرسنگی)\n"
        "/play cat_id — بازی کردن با گربه (افزایش شادی، XP)\n"
        "/rename cat_id name — عوض کردن اسم گربه\n"
        "/customcat cat_id متن_ظاهر — تنظیم ظاهر/اسکین متنی برای گربه\n"
        "/train cat_id stat — ارتقای استت (power / agility / luck)\n"
        "/shop — نمایش آیتم‌های فروشگاه گربه\n"
        "/buygear cat_id item_code — خرید و equip کردن آیتم روی گربه\n"
        "/fight my_cat_id enemy_cat_id — جنگ بین دو گربه (از لول ۹ به بالا)\n"
        "/transfer cat_id @username — انتقال گربه به بازیکن دیگر\n"
    )
    await bot.send_message(message.chat.id, text)


# --- mew (plain text) ---

@dp.message_handler(lambda m: m.text and m.text.strip().lower() == "mew")
async def handle_mew(message: types.Message):
    await maybe_trigger_random_event(message)

    user_tg = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id

    user_db_id = get_or_create_user(user_tg, username)
    register_user_group(user_db_id, chat_id)

    # passive income first
    passive = apply_passive_income(user_tg, user_db_id)

    u = get_user(user_tg)
    now = int(time.time())
    last_mew = u.get("last_mew_ts") or 0
    diff = now - int(last_mew)

    if diff < MEW_COOLDOWN:
        remaining = MEW_COOLDOWN - diff
        mins = remaining // 60
        secs = remaining % 60
        text = (
            f"هنوز باید {mins} دقیقه و {secs} ثانیه صبر کنی تا دوباره میو بزنی 😼"
        )
        if passive > 0:
            text += f"\n(در این مدت {passive} میوپوینت غیرفعال هم گرفتی 💤)"
        await bot.send_message(chat_id, text)
        return

    gained = random.randint(1, 5)
    cur_points = u.get("mew_points") or 0
    new_points = cur_points + gained

    update_user_mew(user_tg, mew_points=new_points, last_mew_ts=now)

    extra = ""
    if passive > 0:
        extra = f"\nهمچنین {passive} امتیاز غیرفعال از گربه‌هات گرفتی 💤"

    await bot.send_message(
        chat_id,
        f"مِیو! 😺\n"
        f"این بار <b>{gained}</b> امتیاز گرفتی و الان <b>{new_points}</b> میوپوینت داری.{extra}",
    )


@dp.message_handler(commands=["profile"])
async def cmd_profile(message: types.Message):
    await maybe_trigger_random_event(message)

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    passive = apply_passive_income(user_tg, user_db_id)

    u = get_user(user_tg)
    cats = get_user_cats(user_db_id)
    mew_points = (u.get("mew_points") or 0) if u else 0
    cat_count = len(cats) if cats else 0

    total_mph = 0.0
    for cat in cats:
        total_mph += compute_cat_mph(cat)

    text = (
        f"🐾 پروفایل {message.from_user.full_name}\n\n"
        f"امتیاز میو: <b>{mew_points}</b>\n"
        f"تعداد گربه‌ها: <b>{cat_count}</b>\n"
        f"مجموع meow/hour گربه‌ها: <b>{total_mph:.1f}</b>\n"
    )
    if passive > 0:
        text += f"\nدر این بازدید {passive} میوپوینت غیرفعال هم گرفتی 💤"

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
    passive = apply_passive_income(user_tg, user_db_id)

    u = get_user(user_tg)
    mew_points = (u.get("mew_points") or 0) if u else 0

    args = (message.get_args() or "").strip().lower()
    if args and args in RARITY_CONFIG:
        rarity = args
    else:
        rarity = choose_rarity()

    conf = RARITY_CONFIG[rarity]
    cost = conf["price"]

    if mew_points < cost:
        await bot.send_message(
            chat_id,
            f"برای گربه‌ی {rarity_emoji(rarity)} ({rarity}) حداقل {cost} امتیاز لازم داری.\n"
            f"الان {mew_points} میوپوینت داری.",
        )
        return

    personality = random.choice(PERSONALITIES)
    element = random.choice(ELEMENTS)
    trait = random.choice(TRAITS)
    name = f"{rarity.title()} Cat"
    description = f"یک گربه‌ی {rarity} با شخصیت {personality}، عنصر {element} و خوی {trait}."

    cat_id = add_cat(user_db_id, name, rarity, personality, element, trait, description)
    update_user_mew(user_tg, mew_points=mew_points - cost)

    text = (
        f"🎉 یک گربه‌ی جدید گرفتی!\n\n"
        f"{rarity_emoji(rarity)} <b>{name}</b> ({rarity})\n"
        f"شخصیت: {personality}\n"
        f"عنصر: {element}\n"
        f"ویژگی: {trait}\n"
        f"ID گربه: <b>{cat_id}</b>\n\n"
        f"{cost} امتیاز خرج شد؛ الان {mew_points - cost} میوپوینت داری."
    )
    if passive > 0:
        text += f"\n(در حین خرید {passive} میوپوینت غیرفعال هم گرفتی 💤)"

    await bot.send_message(chat_id, text)


@dp.message_handler(commands=["cats"])
async def cmd_cats(message: types.Message):
    await maybe_trigger_random_event(message)

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    apply_passive_income(user_tg, user_db_id)

    cats = get_user_cats(user_db_id)
    if not cats:
        await bot.send_message(message.chat.id, "هنوز هیچ گربه‌ای نداری 😿\nبا /adopt یک گربه بگیر.")
        return

    lines = ["🐱 لیست گربه‌های تو:\n"]
    for cat in cats:
        cat = apply_cat_tick(cat)
        stats = compute_cat_effective_stats(cat)
        mph = compute_cat_mph(cat)
        gear_codes = parse_gear_codes(cat.get("gear"))
        gear_text = ", ".join(GEAR_ITEMS[c]["name"] for c in gear_codes if c in GEAR_ITEMS)
        if not gear_text:
            gear_text = "—"

        lines.append(
            f"ID: {cat['id']} — {rarity_emoji(cat['rarity'])} {cat['name']} ({cat['rarity']})\n"
            f"🍗 گرسنگی: {cat['hunger']}/100 | 😊 خوشحالی: {cat['happiness']}/100\n"
            f"⬆️ لول: {cat['level']} (XP: {cat['xp']}/{XP_PER_LEVEL})\n"
            f"⚔️ قدرت: {stats['power']} | 🌀 چابکی: {stats['agility']} | 🍀 شانس: {stats['luck']}\n"
            f"💰 meow/hour: {mph:.1f}\n"
            f"تجهیزات: {gear_text}\n"
            f"توضیحات: {cat['description']}\n"
            "-------------------------"
        )

        # persist decay changes
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
        await bot.send_message(message.chat.id, "استفاده درست: /feed cat_id amount")
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

    apply_passive_income(user_tg, user_db_id)
    u = get_user(user_tg)
    mew_points = (u.get("mew_points") or 0) if u else 0

    cost = amount  # 1 point per 1 hunger
    if mew_points < cost:
        await bot.send_message(
            message.chat.id,
            f"برای این مقدار غذا حداقل {cost} امتیاز لازم داری، الان {mew_points} داری.",
        )
        return

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    cat = apply_cat_tick(cat)

    hunger_before = cat["hunger"]
    hunger_after = min(100, hunger_before + amount)
    happy_after = min(100, cat["happiness"] + amount // 3)

    update_cat_stats(
        cat_id=cat["id"],
        owner_id=user_db_id,
        hunger=hunger_after,
        happiness=happy_after,
        last_tick_ts=int(time.time()),
    )
    update_user_mew(user_tg, mew_points=mew_points - cost)

    if FEED_GIFS:
        await bot.send_animation(message.chat.id, random.choice(FEED_GIFS))

    await bot.send_message(
        message.chat.id,
        f"گربه‌ی <b>{cat['name']}</b> غذاشو خورد 😺\n\n"
        f"🍗 گرسنگی: {hunger_before} ➜ {hunger_after}\n"
        f"😊 خوشحالی: {cat['happiness']} ➜ {happy_after}\n"
        f"💰 {cost} میوپوینت خرج شد؛ الان {mew_points - cost} امتیاز داری.",
    )


@dp.message_handler(commands=["play"])
async def cmd_play(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split()
    if len(args) != 1:
        await bot.send_message(message.chat.id, "استفاده درست: /play cat_id")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id باید عدد باشد.")
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    apply_passive_income(user_tg, user_db_id)

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    cat = apply_cat_tick(cat)

    happy_before = cat["happiness"]
    hunger_before = cat["hunger"]
    xp_before = cat["xp"]
    level_before = cat["level"]

    happy_after = min(100, happy_before + 15)
    hunger_after = max(0, hunger_before - 5)

    xp_after = xp_before + 20
    level_after = level_before
    leveled_up = False
    while xp_after >= XP_PER_LEVEL:
        xp_after -= XP_PER_LEVEL
        level_after += 1
        leveled_up = True

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
        f"⬆️ لول: {level_before} ➜ {level_after} (XP: {xp_after}/{XP_PER_LEVEL})"
    )
    if leveled_up:
        text += "\n🎉 گربه‌ات لول‌آپ شد! این یعنی meow/hour بیشتر و دسترسی به تجهیزات بهتر."

    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=["rename"])
async def cmd_rename(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split(maxsplit=1)
    if len(args) != 2:
        await bot.send_message(message.chat.id, "استفاده درست: /rename cat_id name")
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
    apply_passive_income(user_tg, user_db_id)

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    rename_cat(user_db_id, cat_id, new_name)
    await bot.send_message(
        message.chat.id,
        f"اسم گربه از <b>{cat['name']}</b> به <b>{new_name}</b> تغییر کرد 😺",
    )


@dp.message_handler(commands=["customcat"])
async def cmd_customcat(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split(maxsplit=1)
    if len(args) != 2:
        await bot.send_message(message.chat.id, "استفاده درست: /customcat cat_id ظاهر")
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
    apply_passive_income(user_tg, user_db_id)

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
        f"ظاهر گربه‌ی <b>{cat['name']}</b> به «{appearance}» تغییر کرد 😺",
    )


@dp.message_handler(commands=["train"])
async def cmd_train(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split()
    if len(args) != 2:
        await bot.send_message(
            message.chat.id,
            "استفاده درست: /train cat_id stat\n"
            "stat می‌تونه یکی از power / agility / luck باشه.",
        )
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id باید عدد باشد.")
        return

    stat = args[1].lower()
    if stat not in ("power", "agility", "luck"):
        await bot.send_message(
            message.chat.id,
            "استت باید یکی از power / agility / luck باشد.",
        )
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    apply_passive_income(user_tg, user_db_id)

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    u = get_user(user_tg)
    mew_points = (u.get("mew_points") or 0) if u else 0

    current_val = int(cat.get(f"stat_{stat}", 1))
    new_val = current_val + 1
    cost = 100 * new_val  # هر چه بالاتر، گران‌تر

    if mew_points < cost:
        await bot.send_message(
            message.chat.id,
            f"برای ارتقای {stat} به {new_val} حداقل {cost} امتیاز لازم داری، الان {mew_points} داری.",
        )
        return

    kwargs = {
        "stat_power": None,
        "stat_agility": None,
        "stat_luck": None,
    }
    kwargs[f"stat_{stat}"] = new_val

    update_cat_stats(cat_id=cat_id, owner_id=user_db_id, **kwargs)
    update_user_mew(user_tg, mew_points=mew_points - cost)

    await bot.send_message(
        message.chat.id,
        f"استت {stat} گربه‌ی <b>{cat['name']}</b> از {current_val} به {new_val} رسید.\n"
        f"💰 {cost} میوپوینت خرج شد؛ الان {mew_points - cost} امتیاز داری.",
    )


@dp.message_handler(commands=["shop"])
async def cmd_shop(message: types.Message):
    await maybe_trigger_random_event(message)

    lines = ["🛒 فروشگاه تجهیزات گربه:\n"]
    for code, item in GEAR_ITEMS.items():
        lines.append(
            f"{item['name']} (کد: {code})\n"
            f"قیمت: {item['price']} میوپوینت\n"
            f"+{item['mph_bonus']} meow/hour، "
            f"+{item['power_bonus']} قدرت، "
            f"+{item['agility_bonus']} چابکی، "
            f"+{item['luck_bonus']} شانس\n"
            "-------------------------"
        )

    lines.append("برای خرید: /buygear cat_id item_code")
    await bot.send_message(message.chat.id, "\n".join(lines))


@dp.message_handler(commands=["buygear"])
async def cmd_buygear(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split()
    if len(args) != 2:
        await bot.send_message(message.chat.id, "استفاده درست: /buygear cat_id item_code")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id باید عدد باشد.")
        return

    code = args[1].lower()
    if code not in GEAR_ITEMS:
        await bot.send_message(message.chat.id, "item_code نامعتبر است. /shop را چک کن.")
        return

    item = GEAR_ITEMS[code]

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    apply_passive_income(user_tg, user_db_id)

    cat = get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    if cat["level"] < 3:
        await bot.send_message(
            message.chat.id,
            "برای استفاده از تجهیزات، گربه باید حداقل لول ۳ باشد.",
        )
        return

    u = get_user(user_tg)
    mew_points = (u.get("mew_points") or 0) if u else 0
    price = item["price"]

    if mew_points < price:
        await bot.send_message(
            message.chat.id,
            f"برای {item['name']} حداقل {price} امتیاز لازم داری، الان {mew_points} داری.",
        )
        return

    gear_codes = parse_gear_codes(cat.get("gear"))
    if code in gear_codes:
        await bot.send_message(
            message.chat.id,
            "این آیتم را قبلاً روی این گربه نصب کرده‌ای.",
        )
        return

    gear_codes.append(code)
    new_gear_str = ",".join(gear_codes)

    update_cat_stats(cat_id=cat_id, owner_id=user_db_id, gear=new_gear_str)
    update_user_mew(user_tg, mew_points=mew_points - price)

    mph = compute_cat_mph({**cat, "gear": new_gear_str})
    await bot.send_message(
        message.chat.id,
        f"{item['name']} روی گربه‌ی <b>{cat['name']}</b> equip شد 😺\n"
        f"💰 {price} میوپوینت خرج شد؛ الان {mew_points - price} امتیاز داری.\n"
        f"meow/hour جدید این گربه: {mph:.1f}",
    )


@dp.message_handler(commands=["fight"])
async def cmd_fight(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split()
    if len(args) != 2:
        await bot.send_message(message.chat.id, "استفاده درست: /fight my_cat_id enemy_cat_id")
        return

    try:
        my_id = int(args[0])
        enemy_id = int(args[1])
    except ValueError:
        await bot.send_message(message.chat.id, "هر دو cat_id باید عدد باشند.")
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    my_db_id = get_or_create_user(user_tg, username)
    apply_passive_income(user_tg, my_db_id)

    my_cat = get_cat(my_id, owner_id=my_db_id)
    if not my_cat:
        await bot.send_message(message.chat.id, "گربه‌ی اول مال تو نیست یا وجود ندارد.")
        return

    # enemy cat can belong to anyone
    enemy_cat = get_cat(enemy_id)
    if not enemy_cat:
        await bot.send_message(message.chat.id, "گربه‌ی دوم وجود ندارد.")
        return

    if my_cat["level"] < 9 or enemy_cat["level"] < 9:
        await bot.send_message(
            message.chat.id,
            "برای جنگ، هر دو گربه باید حداقل لول ۹ باشند.",
        )
        return

    # compute stats
    my_stats = compute_cat_effective_stats(my_cat)
    enemy_stats = compute_cat_effective_stats(enemy_cat)

    my_score = 0
    enemy_score = 0

    battle_log = []

    for round_idx in range(1, 4):
        my_roll = (
            my_stats["power"] * 1.5
            + my_stats["agility"] * random.uniform(0.5, 1.2)
            + my_stats["luck"] * random.uniform(0.0, 1.5)
        )
        enemy_roll = (
            enemy_stats["power"] * 1.5
            + enemy_stats["agility"] * random.uniform(0.5, 1.2)
            + enemy_stats["luck"] * random.uniform(0.0, 1.5)
        )
        if my_roll > enemy_roll:
            my_score += 1
            battle_log.append(f"راند {round_idx}: گربه‌ی تو برنده شد 💥")
        elif enemy_roll > my_roll:
            enemy_score += 1
            battle_log.append(f"راند {round_idx}: گربه‌ی حریف برنده شد 💢")
        else:
            battle_log.append(f"راند {round_idx}: مساوی شد 😼")

    u = get_user(user_tg)
    mew_points = (u.get("mew_points") or 0) if u else 0

    if my_score > enemy_score:
        result = "🏆 گربه‌ی تو برنده‌ی نبرد شد!"
        xp_gain = 30
        reward_points = 50
        new_xp = my_cat["xp"] + xp_gain
        level = my_cat["level"]
        leveled_up = False
        while new_xp >= XP_PER_LEVEL:
            new_xp -= XP_PER_LEVEL
            level += 1
            leveled_up = True

        update_cat_stats(
            cat_id=my_cat["id"],
            owner_id=my_db_id,
            xp=new_xp,
            level=level,
            happiness=min(100, my_cat["happiness"] + 10),
            last_tick_ts=int(time.time()),
        )
        update_user_mew(user_tg, mew_points=mew_points + reward_points)

        extra = f"\nXP +{xp_gain} و {reward_points} میوپوینت گرفتی."
        if leveled_up:
            extra += "\n🎉 گربه‌ات لول‌آپ شد!"
    elif enemy_score > my_score:
        result = "😿 گربه‌ی تو باخت."
        # small happiness loss
        update_cat_stats(
            cat_id=my_cat["id"],
            owner_id=my_db_id,
            happiness=max(0, my_cat["happiness"] - 10),
            last_tick_ts=int(time.time()),
        )
        extra = "\nگربه‌ات کمی ناراحت شد (۱۰ خوشحالی کم شد)."
    else:
        result = "🤝 نبرد مساوی شد."
        extra = ""

    text = (
        f"نبرد بین <b>{my_cat['name']}</b> و <b>{enemy_cat['name']}</b> شروع شد!\n\n"
        + "\n".join(battle_log)
        + "\n\n"
        + result
        + extra
    )

    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=["transfer"])
async def cmd_transfer(message: types.Message):
    await maybe_trigger_random_event(message)

    args = (message.get_args() or "").split()
    if len(args) != 2:
        await bot.send_message(message.chat.id, "استفاده درست: /transfer cat_id @username")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await bot.send_message(message.chat.id, "cat_id باید عدد باشد.")
        return

    target_username = args[1].lstrip("@").strip()
    if not target_username:
        await bot.send_message(message.chat.id, "یوزرنیم هدف نامعتبر است.")
        return

    user_tg = message.from_user.id
    username = message.from_user.username
    from_db_id = get_or_create_user(user_tg, username)
    apply_passive_income(user_tg, from_db_id)

    cat = get_cat(cat_id, owner_id=from_db_id)
    if not cat:
        await bot.send_message(message.chat.id, "گربه‌ای با این ID پیدا نشد یا مال تو نیست.")
        return

    all_users = get_all_users()
    target_row = None
    for u in all_users:
        if (u.get("username") or "").lower() == target_username.lower():
            target_row = u
            break

    if not target_row:
        await bot.send_message(
            message.chat.id,
            "کاربر هدف هنوز با بات کار نکرده یا توی دیتابیس نیست.\n"
            "بهش بگو یک /start برای بات بفرسته و دوباره امتحان کن.",
        )
        return

    to_db_id = target_row["id"]
    set_cat_owner(cat_id, to_db_id)

    await bot.send_message(
        message.chat.id,
        f"گربه‌ی <b>{cat['name']}</b> با ID {cat_id} منتقل شد به @{target_username} 😼",
    )


# ========= catch-all for emoji events =========

@dp.message_handler()
async def catch_all(message: types.Message):
    handled = await process_event_answer(message)
    if handled:
        return
    # rest of random chat is ignored by bot
    return


# ========= webhook server =========

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
