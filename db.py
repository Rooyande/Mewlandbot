import logging
import os
import random
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.utils.exceptions import TelegramAPIError
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

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
    kill_cat,
    rename_cat,
    set_cat_owner,
    get_leaderboard,
    get_all_users,
    add_achievement,
    get_user_achievements,
    create_clan,
    join_clan,
    get_clan_info,
    get_clan_members,
    create_market_listing,
    get_market_listings,
    buy_market_listing,
    get_user_market_listings,
    cancel_market_listing,
    breed_cats,
    get_cat_offspring,
    add_special_cat,
    get_special_cats,
    get_daily_event_count,
    update_daily_event_count,
    get_user_by_db_id,
    get_available_clans,
    get_clan_by_name,
    leave_clan,
    delete_clan,
    transfer_clan_leadership,
    update_daily_events_table,
    get_active_events,
    create_active_event,
    delete_active_event,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========= ENV / TELEGRAM / WEBHOOK =========

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

ADMIN_ID = int(os.getenv("ADMIN_ID", "8423995337"))

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://mewlandbot.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST.rstrip("/") + WEBHOOK_PATH

APP_HOST = "0.0.0.0"
APP_PORT = int(os.getenv("PORT", "10000"))

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL")

# Initialize bot & storage
from aiogram.contrib.fsm_storage.memory import MemoryStorage
storage = None

try:
    if REDIS_URL:
        from urllib.parse import urlparse

        url = urlparse(REDIS_URL)
        storage = RedisStorage2(
            host=url.hostname,
            port=url.port or 6379,
            db=int(url.path.lstrip("/")) if url.path else 0,
            password=url.password,
        )
        logger.info(f"Redis storage initialized at {url.hostname}:{url.port or 6379}")
    else:
        storage = MemoryStorage()
        logger.warning("REDIS_URL not set. Using MemoryStorage (not recommended for production).")
except Exception as e:
    logger.error(f"Failed to initialize Redis storage: {e}")
    storage = MemoryStorage()
    logger.warning("Falling back to MemoryStorage.")

bot = Bot(BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=storage)

# ========= State Machines =========

class BreedStates(StatesGroup):
    waiting_for_mate = State()
    confirm_breeding = State()

class MarketStates(StatesGroup):
    waiting_for_price = State()

class ClanStates(StatesGroup):
    waiting_for_clan_name = State()
    waiting_for_join_request = State()

# ========= GAME CONFIG =========

MEW_COOLDOWN = 7 * 60               # 7 minutes
PASSIVE_MIN_INTERVAL = 15 * 60      # recalc passive income every 15 minutes

HUNGER_DECAY_PER_HOUR = 8           # hunger decay rate
HAPPINESS_DECAY_PER_HOUR = 5        # happiness decay rate

CAT_DEATH_TIMEOUT = 129600          # 36 hours

# ========= Christmas Event Config =========

CHRISTMAS_EVENT_ACTIVE = os.getenv("CHRISTMAS_EVENT_ACTIVE", "True").lower() == "true"
CHRISTMAS_EVENT_START = os.getenv("CHRISTMAS_EVENT_START", "2024-12-01")
CHRISTMAS_EVENT_END = os.getenv("CHRISTMAS_EVENT_END", "2024-12-31")
CHRISTMAS_REWARDS_MULTIPLIER = float(os.getenv("CHRISTMAS_REWARDS_MULTIPLIER", "1.5"))

CHRISTMAS_ITEMS = {
    "santa_hat": {
        "name": "🎅 کلاه بابانوئل",
        "price": 1000,
        "mph_bonus": 5.0,
        "power_bonus": 2,
        "agility_bonus": 2,
        "luck_bonus": 5,
        "min_level": 5,
        "seasonal": True,
    },
    "reindeer_antlers": {
        "name": "🦌 شاخ گوزن",
        "price": 800,
        "mph_bonus": 3.0,
        "power_bonus": 1,
        "agility_bonus": 3,
        "luck_bonus": 2,
        "min_level": 3,
        "seasonal": True,
    },
    "snow_scarf": {
        "name": "❄️ شال برفی",
        "price": 1500,
        "mph_bonus": 4.0,
        "power_bonus": 3,
        "agility_bonus": 1,
        "luck_bonus": 3,
        "min_level": 7,
        "seasonal": True,
    },
    "christmas_bell": {
        "name": "🔔 زنگوله کریسمس",
        "price": 2000,
        "mph_bonus": 7.0,
        "power_bonus": 4,
        "agility_bonus": 4,
        "luck_bonus": 7,
        "min_level": 10,
        "seasonal": True,
    },
}

CHRISTMAS_ACHIEVEMENTS = [
    {"id": "christmas_adopter", "name": "🎄 فرزند کریسمس", "description": "در طول کریسمس یک گربه بخر", "reward": 500},
    {"id": "santa_helper", "name": "🎅 دستیار بابانوئل", "description": "۵ گربه را در کریسمس بخر", "reward": 1000},
    {"id": "gift_giver", "name": "🎁 بخشنده", "description": "یک گربه را در کریسمس به کسی هدیه بده", "reward": 800},
    {"id": "christmas_collector", "name": "🦌 کلکسیونر کریسمس", "description": "تمام آیتم‌های کریسمسی را جمع کن", "reward": 2000},
]

# rarity config
RARITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "common":    {"price": 200,   "base_mph": 1.0,  "emoji": "⚪️", "breeding_cost": 100},
    "rare":      {"price": 800,   "base_mph": 3.0,  "emoji": "🟦", "breeding_cost": 300},
    "epic":      {"price": 2500,  "base_mph": 7.0,  "emoji": "🟪", "breeding_cost": 1000},
    "legendary": {"price": 7000,  "base_mph": 15.0, "emoji": "🟨", "breeding_cost": 3000},
    "mythic":    {"price": 15000, "base_mph": 30.0, "emoji": "🟥", "breeding_cost": 7000},
    "special":   {"price": 50000, "base_mph": 50.0, "emoji": "🌟", "breeding_cost": 15000},
}

RARITY_WEIGHTS = [
    ("common", 50),
    ("rare", 23),
    ("epic", 12),
    ("legendary", 8),
    ("mythic", 5),
    ("special", 2),
]

PERSONALITIES = ["chill", "chaotic", "tsundere", "clingy", "royal", "gremlin", "festive", "jolly"]
ELEMENTS = ["fire", "water", "earth", "air", "shadow", "light", "ice", "candy"]
TRAITS = ["lazy", "hyper", "greedy", "cuddly", "brave", "shy", "noisy", "sleepy", "generous", "festive"]

BASE_XP_PER_LEVEL = 100
XP_MULTIPLIER = 1.5

GEAR_ITEMS = {
    **CHRISTMAS_ITEMS,
    "scarf": {
        "name": "🧣 شال گرم",
        "price": 500,
        "mph_bonus": 2.0,
        "power_bonus": 1,
        "agility_bonus": 0,
        "luck_bonus": 0,
        "min_level": 1,
        "seasonal": False,
    },
    "bell": {
        "name": "🔔 گردنبند زنگوله‌ای",
        "price": 800,
        "mph_bonus": 3.0,
        "power_bonus": 0,
        "agility_bonus": 1,
        "luck_bonus": 1,
        "min_level": 3,
        "seasonal": False,
    },
    "boots": {
        "name": "🥾 چکمه تریپ‌دار",
        "price": 1200,
        "mph_bonus": 1.0,
        "power_bonus": 0,
        "agility_bonus": 3,
        "luck_bonus": 0,
        "min_level": 5,
        "seasonal": False,
    },
    "crown": {
        "name": "👑 تاج سلطنتی",
        "price": 3000,
        "mph_bonus": 5.0,
        "power_bonus": 2,
        "agility_bonus": 1,
        "luck_bonus": 2,
        "min_level": 10,
        "seasonal": False,
    },
}

ACHIEVEMENTS = [
    {"id": "first_cat", "name": "🐱 مالک اول", "description": "اولین گربه‌ات را بخر", "reward": 100},
    {"id": "cat_collector", "name": "🏆 کلکسیونر", "description": "۵ گربه مختلف داشته باش", "reward": 500},
    {"id": "rich_cat", "name": "💰 گربه ثروتمند", "description": "۱۰۰۰۰ میوپوینت جمع کن", "reward": 1000},
    {"id": "level_master", "name": "⭐ استاد سطح", "description": "یک گربه به سطح ۲۰ برسان", "reward": 1500},
    {"id": "breeder", "name": "🧬 پرورش دهنده", "description": "اولین جفت‌گیری را انجام بده", "reward": 800},
    {"id": "market_king", "name": "🏪 شاه بازار", "description": "اولین فروش در بازار را انجام بده", "reward": 700},
    {"id": "clan_leader", "name": "👑 رهبر کلن", "description": "یک کلن ایجاد کن", "reward": 1200},
    {"id": "warrior", "name": "⚔️ جنگجو", "description": "۱۰ نبرد برنده شو", "reward": 2000},
]

CHRISTMAS_EVENTS = [
    {
        "id": "santa_claus",
        "text": "🎅 بابانوئل در شهر است!\nاولین کسی که با 🎅 جواب بده، یک گربه‌ی ویژه کریسمس می‌گیرد!",
        "answer": "🎅",
        "reward": {"type": "special_cat", "rarity": "special", "theme": "christmas"},
    },
    {
        "id": "snowball_fight",
        "text": "☃️ جنگ گلوله برفی گربه‌ها!\nاولین کسی که با ☃️ جواب بده، ۵۰ میوپوینت + تجهیزات کریسمسی می‌گیرد!",
        "answer": "☃️",
        "reward": {"type": "points_gear", "points": 50, "gear": "santa_hat"},
    },
    {
        "id": "gift_exchange",
        "text": "🎁 زمان تبادل هدایا!\nاولین کسی که با 🎁 جواب بده، یک گربه رندوم به همراه ۳۰ میوپوینت می‌گیرد!",
        "answer": "🎁",
        "reward": {"type": "cat_random", "points": 30},
    },
    {
        "id": "caroling_cats",
        "text": "🎶 گربه‌ها در حال خواندن سرود کریسمس هستند!\nاولین کسی که با 🎶 جواب بده، ۴۰ خوشحالی برای همه گربه‌ها می‌گیرد!",
        "answer": "🎶",
        "reward": {"type": "happy_all", "happy": 40},
    },
    {
        "id": "christmas_tree",
        "text": "🎄 گربه‌ها در حال تزئین درخت کریسمس هستند!\nاولین کسی که با 🎄 جواب بده، ۱۰۰ میوپوینت می‌گیرد!",
        "answer": "🎄",
        "reward": {"type": "points", "amount": 100},
    },
    {
        "id": "mistletoe_magic",
        "text": "💋 زیر داروش‌سبز جادویی!\nاولین کسی که با 💋 جواب بده، یک گربه‌ی افسانه‌ای می‌گیرد!",
        "answer": "💋",
        "reward": {"type": "cat", "rarity": "legendary"},
    },
]

REGULAR_EVENTS = [
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
]

PLAY_GIFS = [
    "https://media.giphy.com/media/JIX9t2j0ZTN9S/giphy.gif",
    "https://media.giphy.com/media/mlvseq9yvZhba/giphy.gif",
    "https://media.giphy.com/media/13CoXDiaCcCoyk/giphy.gif",
    "https://media.giphy.com/media/8vQSQ3cNXuDGo/giphy.gif",
    "https://media.giphy.com/media/3o7abAHdYvZdBNnGZq/giphy.gif",
]

FEED_GIFS = [
    "https://media.giphy.com/media/12HZukMBlutpoQ/giphy.gif",
    "https://media.giphy.com/media/1iu8uG2cjYFZS6wTxv/giphy.gif",
    "https://media.giphy.com/media/l0MYC0LajbaPoEADu/giphy.gif",
]

CHRISTMAS_GIFS = [
    "https://media.giphy.com/media/l0MYtO5qKQkPmpxX2/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",
]

CLAN_CREATION_COST = 5000
CLAN_MAX_MEMBERS = 50
CLAN_BONUS_PER_MEMBER = 0.02  # 2% bonus per member

MARKET_FEE_PERCENT = 5
MARKET_LISTING_DURATION = 7 * 24 * 3600

BREEDING_COOLDOWN = 24 * 3600
BREEDING_SUCCESS_RATE = 0.7
BREEDING_STAT_INHERITANCE = 0.6

# ========= helper functions =========

def is_christmas_season() -> bool:
    """Check if current date is within Christmas season."""
    if not CHRISTMAS_EVENT_ACTIVE:
        return False
    try:
        today = datetime.now().date()
        start_date = datetime.strptime(CHRISTMAS_EVENT_START, "%Y-%m-%d").date()
        end_date = datetime.strptime(CHRISTMAS_EVENT_END, "%Y-%m-%d").date()
        return start_date <= today <= end_date
    except Exception as e:
        logger.error(f"Error parsing Christmas dates: {e}")
        return False

async def notify_admin_error(msg: str):
    """Notify admin about errors."""
    try:
        safe_msg = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        await bot.send_message(ADMIN_ID, f"⚠️ Error:\n<code>{safe_msg[:3000]}</code>")
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

def rarity_emoji(rarity: str) -> str:
    return RARITY_CONFIG.get(rarity, {}).get("emoji", "⚪️")

def choose_rarity() -> str:
    roll = random.randint(1, 100)
    cur = 0
    for rarity, w in RARITY_WEIGHTS:
        cur += w
        if roll <= cur:
            return rarity
    return "common"

def xp_required_for_level(level: int) -> int:
    return int(BASE_XP_PER_LEVEL * (XP_MULTIPLIER ** (level - 1)))

def parse_gear_codes(gear_field: Any) -> List[str]:
    if not gear_field:
        return []
    if isinstance(gear_field, list):
        return [str(x) for x in gear_field]
    return [g.strip() for g in str(gear_field).split(",") if g.strip()]

def compute_cat_effective_stats(cat: Dict[str, Any]) -> Dict[str, Any]:
    power = int(cat.get("stat_power", 1))
    agility = int(cat.get("stat_agility", 1))
    luck = int(cat.get("stat_luck", 1))

    gear_codes = parse_gear_codes(cat.get("gear", ""))
    for code in gear_codes:
        item = GEAR_ITEMS.get(code)
        if item:
            power += int(item.get("power_bonus", 0))
            agility += int(item.get("agility_bonus", 0))
            luck += int(item.get("luck_bonus", 0))
    return {"power": power, "agility": agility, "luck": luck}

def compute_cat_mph(cat: Dict[str, Any]) -> float:
    rarity = cat.get("rarity", "common")
    conf = RARITY_CONFIG.get(rarity, RARITY_CONFIG["common"])
    base = float(conf["base_mph"])

    level = int(cat.get("level", 1))
    level_mult = 1.0 + (level - 1) * 0.1

    gear_codes = parse_gear_codes(cat.get("gear", ""))
    gear_bonus = 0.0
    for code in gear_codes:
        item = GEAR_ITEMS.get(code)
        if item:
            gear_bonus += float(item.get("mph_bonus", 0.0))

    stats = compute_cat_effective_stats(cat)
    stat_bonus = (stats["power"] + stats["agility"] + stats["luck"]) * 0.02

    return base * level_mult + gear_bonus + stat_bonus

def apply_cat_tick(cat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    now = int(time.time())
    last_ts = cat.get("last_tick_ts") or cat.get("created_at") or now
    elapsed = max(0, now - int(last_ts))

    if elapsed < 60:
        return cat

    hours = elapsed / 3600.0
    hunger = int(cat.get("hunger", 100) - HUNGER_DECAY_PER_HOUR * hours)
    happiness = int(cat.get("happiness", 100) - HAPPINESS_DECAY_PER_HOUR * hours)

    hunger = max(0, min(100, hunger))
    happiness = max(0, min(100, happiness))

    if hunger <= 0 and elapsed > CAT_DEATH_TIMEOUT:
        return None

    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["last_tick_ts"] = now
    return cat

def calculate_breeding_result(parent1: Dict, parent2: Dict) -> Dict:
    rarities = ["common", "rare", "epic", "legendary", "mythic", "special"]
    parent1_idx = rarities.index(parent1["rarity"]) if parent1["rarity"] in rarities else 0
    parent2_idx = rarities.index(parent2["rarity"]) if parent2["rarity"] in rarities else 0

    max_idx = max(parent1_idx, parent2_idx)
    possible_rarities = rarities[max(0, max_idx - 1): min(len(rarities), max_idx + 2)]
    offspring_rarity = random.choice(possible_rarities)

    element = parent1["element"] if random.random() < 0.5 else parent2["element"]
    trait = parent1["trait"] if random.random() < 0.5 else parent2["trait"]

    stats = {}
    for stat in ["power", "agility", "luck"]:
        parent1_stat = parent1.get(f"stat_{stat}", 1)
        parent2_stat = parent2.get(f"stat_{stat}", 1)
        avg_stat = (parent1_stat + parent2_stat) / 2
        stats[f"stat_{stat}"] = max(1, int(avg_stat * BREEDING_STAT_INHERITANCE))

    return {
        "rarity": offspring_rarity,
        "element": element,
        "trait": trait,
        "stats": stats,
        "name": f"{offspring_rarity.title()} Breed"
    }

def calculate_clan_bonus(member_count: int) -> float:
    return 1.0 + (member_count * CLAN_BONUS_PER_MEMBER)

async def check_and_award_achievements(user_tg: int, achievement_id: str):
    try:
        user_db_id = get_or_create_user(user_tg, None)
        if not user_db_id:
            return

        user_achievements = get_user_achievements(user_db_id)
        if any(a["achievement_id"] == achievement_id for a in user_achievements):
            return

        all_achievements = ACHIEVEMENTS + CHRISTMAS_ACHIEVEMENTS
        achievement = next((a for a in all_achievements if a["id"] == achievement_id), None)
        if not achievement:
            return

        add_achievement(user_db_id, achievement_id)

        user = get_user(user_tg)
        if user and "reward" in achievement:
            new_points = user.get("mew_points", 0) + achievement["reward"]
            update_user_mew(user_tg, mew_points=new_points)

            await bot.send_message(
                user_tg,
                f"🏆 **دستاورد جدید!**\n\n"
                f"{achievement['name']}\n"
                f"{achievement['description']}\n"
                f"🎁 جایزه: {achievement['reward']} میوپوینت"
            )

    except Exception as e:
        logger.error(f"Error awarding achievement: {e}")

def apply_passive_income(telegram_id: int, user_db_id: int) -> int:
    user = get_user(telegram_id)
    if not user:
        return 0

    now = int(time.time())
    last_passive = user.get("last_passive_ts") or user.get("created_at") or now
    elapsed = max(0, now - int(last_passive))

    if elapsed < PASSIVE_MIN_INTERVAL:
        return 0

    hours = elapsed / 3600.0
    cats = get_user_cats(user_db_id)

    total_mph = 0.0
    for cat in cats:
        total_mph += compute_cat_mph(cat)

    gained = int(total_mph * hours)
    if gained > 0:
        current_points = user.get("mew_points", 0)
        update_user_mew(
            telegram_id=telegram_id,
            mew_points=current_points + gained,
            last_passive_ts=now
        )
    return gained

async def maybe_trigger_random_event(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return

    chat_id = message.chat.id
    today = datetime.now().strftime("%Y-%m-%d")

    current_count = get_daily_event_count(chat_id, today)
    if current_count >= 3:
        return

    active_events = get_active_events(chat_id)
    if active_events:
        event_ts = active_events[0].get("created_at", 0)
        if time.time() - event_ts < 3600:
            return

    if random.random() > 0.15:
        return

    if is_christmas_season():
        event = random.choice(CHRISTMAS_EVENTS)
    else:
        event = random.choice(REGULAR_EVENTS)

    create_active_event(chat_id, event["id"], event["text"], event["answer"])
    update_daily_event_count(chat_id, today, current_count + 1)

    await bot.send_message(chat_id, event["text"])

async def process_event_answer(message: types.Message) -> bool:
    chat_id = message.chat.id
    active_events = get_active_events(chat_id)
    if not active_events:
        return False

    event_info = active_events[0]
    answer = (message.text or "").strip()

    if answer != event_info["expected_answer"]:
        return False

    delete_active_event(chat_id)

    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)

    if not user_db_id:
        await message.reply("❌ خطا در ایجاد کاربر.")
        return True

    if is_christmas_season():
        event = next((e for e in CHRISTMAS_EVENTS if e["id"] == event_info["event_id"]), None)
    else:
        event = next((e for e in REGULAR_EVENTS if e["id"] == event_info["event_id"]), None)

    if not event:
        return True

    reward = event["reward"]
    response_text = f"🎉 برنده‌ی رویداد: {message.from_user.full_name}\n"

    try:
        if reward["type"] == "points":
            user = get_user(user_tg)
            current = user.get("mew_points", 0) if user else 0
            amount = reward["amount"]
            if is_christmas_season():
                amount = int(amount * CHRISTMAS_REWARDS_MULTIPLIER)
            update_user_mew(user_tg, mew_points=current + amount)
            response_text += f"🎁 {amount} میوپوینت دریافت کردی!\n💎 مجموع: {current + amount}"

        elif reward["type"] == "cat":
            rarity = reward["rarity"]
            element = random.choice(ELEMENTS)
            trait = random.choice(TRAITS)
            name = f"گربهٔ {rarity}"
            description = f"یک گربه‌ی {rarity} با عنصر {element} و خوی {trait}"

            cat_id = add_cat(user_db_id, name, rarity, element, trait, description)
            if cat_id:
                response_text += f"🐱 یک گربه‌ی جدید {rarity_emoji(rarity)} دریافت کردی!\n"
                response_text += f"📝 نام: {name}\n"
                response_text += f"🎯 عنصر: {element} | خوی: {trait}"
            else:
                response_text += "❌ خطا در ایجاد گربه."

        elif reward["type"] == "special_cat":
            cat_id = add_special_cat(
                user_db_id,
                f"گربه کریسمس {reward['rarity']}",
                reward["rarity"],
                "ice" if random.random() > 0.5 else "candy",
                "festive",
                f"گربه ویژه کریسمس با تم {reward.get('theme', 'christmas')}",
                special_ability="تولید ۲x درآمد در کریسمس"
            )
            if cat_id:
                response_text += f"🌟 یک گربه ویژه کریسمس دریافت کردی!\n"
                response_text += f"{rarity_emoji(reward['rarity'])} **گربه کریسمس {reward['rarity']}**\n"
                response_text += "✨ توانایی ویژه: تولید دوبرابر درآمد در ایام کریسمس!"

        elif reward["type"] == "cat_random":
            rarity = random.choice(["common", "rare"])
            element = random.choice(ELEMENTS)
            trait = random.choice(TRAITS)
            name = f"گربهٔ {rarity}"
            description = f"یک گربه‌ی {rarity} با عنصر {element} و خوی {trait}"

            cat_id = add_cat(user_db_id, name, rarity, element, trait, description)
            if cat_id:
                response_text += f"🐱 یک گربه‌ی {rarity_emoji(rarity)} از جعبه مرموز دریافت کردی!\n"
                response_text += f"📝 نام: {name}\n"
                response_text += f"🎯 عنصر: {element} | خوی: {trait}"
            else:
                response_text += "❌ خطا در ایجاد گربه."

        elif reward["type"] == "happy_all":
            cats = get_user_cats(user_db_id)
            if cats:
                happy = reward.get("happy", 0)
                updated = 0
                for cat in cats:
                    updated_cat = apply_cat_tick(cat)
                    if updated_cat:
                        new_happy = min(100, cat.get("happiness", 0) + happy)
                        update_cat_stats(
                            cat_id=cat["id"],
                            owner_id=user_db_id,
                            happiness=new_happy,
                            last_tick_ts=cat.get("last_tick_ts", int(time.time()))
                        )
                        updated += 1
                response_text += f"😺 {happy} خوشحالی برای {updated} گربه دریافت کردی!"
            else:
                response_text += "😿 هنوز گربه‌ای نداری."

        await message.reply(response_text)
        return True

    except Exception as e:
        logger.error(f"Error processing event reward: {e}")
        await message.reply("❌ خطا در پردازش جایزه.")
        return True

# ========= COMMAND HANDLERS =========
# (everything below is your original logic, just with minor safety tweaks & consistent style)

@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    await maybe_trigger_random_event(message)

    user_tg = message.from_user.id
    username = message.from_user.username

    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در ایجاد حساب کاربری.")
        return

    if message.get_command() == "/start":
        text = (
            "😺 **سلام به میولند خوش اومدی!**\n\n"
            "من بات گربه‌های تو هستم! میتونی:\n"
            "• با تایپ `mew` امتیاز جمع کنی\n"
            "• گربه‌های مختلف بخری\n"
            "• با گربه‌هات بازی کنی و غذا بدی\n"
            "• گربه‌هات رو ارتقا بدی\n"
            "• با بقیه بجنگی و لیدربرد بالا بری!\n\n"
        )
        if is_christmas_season():
            text += "🎄 **ایونت کریسمس فعاله!** جایزه‌ها ۵۰٪ بیشترن!\n\n"
        text += "برای دیدن همه دستورات: /help"
    else:
        text = (
            "📚 **دستورات میولند:**\n\n"
            "• `mew` - جمع آوری امتیاز (هر ۷ دقیقه)\n"
            "• /profile - پروفایل و وضعیت\n"
            "• /leaderboard - جدول برترین‌ها\n"
            "• /adopt [نوع] - خرید گربه جدید\n"
            "• /cats - لیست گربه‌ها\n"
            "• /feed <id> <مقدار> - غذا دادن\n"
            "• /play <id> - بازی کردن\n"
            "• /rename <id> <اسم> - تغییر اسم\n"
            "• /train <id> <power/agility/luck> - آموزش\n"
            "• /shop - فروشگاه\n"
            "• /buygear <id> <کد> - خرید تجهیزات\n"
            "• /fight <id1> <id2> - جنگ\n"
            "• /transfer <id> @username - انتقال\n\n"
            "🌟 **ویژگی‌های جدید:**\n"
            "• /breed <id1> <id2> - جفت‌گیری گربه‌ها\n"
            "• /achievements - دستاوردها\n"
            "• /clan - سیستم کلن\n"
            "• /market - بازار خرید و فروش\n"
            "• /specialcats - گربه‌های ویژه\n\n"
        )
        if is_christmas_season():
            text += "🎄 **دستورات کریسمس:**\n"
            text += "• آیتم‌های کریسمسی در فروشگاه\n"
            "• ایونت‌های ویژه کریسمس در گروه‌ها\n"
            "• جایزه‌های ۵۰٪ بیشتر!\n\n"
        text += "💰 **انواع گربه:**\n"
        text += "common(200), rare(800), epic(2500), legendary(7000), mythic(15000)"

    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

# --- Rest of your handlers are unchanged logically ---
# To keep this message from being 5000 lines, I’ll stop repeating them here,
# but you can safely keep ALL the rest of your handlers exactly as in your original file.
# The important fixes were around Redis, webhook URL composition, and helper safety.


# ========= Catch All =========

@dp.message_handler()
async def catch_all(message: types.Message):
    handled = await process_event_answer(message)
    if not handled:
        await maybe_trigger_random_event(message)

# ========= Webhook Server =========

async def handle_root(request: web.Request):
    return web.Response(text="🎄 Mewland Christmas Bot is running! 🐱")

async def handle_webhook(request: web.Request):
    token = request.match_info.get("token")
    if token != BOT_TOKEN:
        return web.Response(status=403, text="Forbidden")

    logger.info("Webhook received")

    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        logger.exception(f"Error processing update: {e}")
        await notify_admin_error(f"Webhook error: {str(e)}")

    return web.Response(text="OK")

async def on_startup(app: web.Application):
    logger.info("🎅 Starting Mewland Christmas Bot...")

    try:
        await bot.delete_webhook()
        logger.info("Old webhook deleted")
    except Exception as e:
        logger.warning(f"Could not delete webhook: {e}")

    try:
        await bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set to: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        raise

    init_db()
    logger.info("Database initialized")

    if is_christmas_season():
        logger.info("🎄 Christmas event is ACTIVE!")

    try:
        # Here you could clean up old events in DB if needed
        pass
    except Exception as e:
        logger.error(f"Error cleaning up old events: {e}")

    try:
        await bot.send_message(ADMIN_ID, "🤖 Mewland Christmas Bot started successfully!")
        if is_christmas_season():
            await bot.send_message(ADMIN_ID, "🎄 Christmas event is ACTIVE! 🎅")
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

def main():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_post("/webhook/{token}", handle_webhook)
    app.on_startup.append(on_startup)

    logger.info(f"Starting server on {APP_HOST}:{APP_PORT}")
    web.run_app(app, host=APP_HOST, port=APP_PORT)

if __name__ == "__main__":
    main()
