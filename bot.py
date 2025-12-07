import logging
import os
import random
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.utils.exceptions import TelegramAPIError
from aiogram.contrib.fsm_storage.memory import MemoryStorage
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

# Initialize bot with storage
storage = MemoryStorage()
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

MEW_COOLDOWN = 7 * 60       # 7 minutes
PASSIVE_MIN_INTERVAL = 15 * 60  # only recalc passive income every 15 minutes

# hunger / happiness decay
HUNGER_DECAY_PER_HOUR = 8   # Increased decay rate
HAPPINESS_DECAY_PER_HOUR = 5

# Cat death thresholds (36 hours = 129600 seconds)
CAT_DEATH_TIMEOUT = 129600

# ========= Christmas Event Config =========

CHRISTMAS_EVENT_ACTIVE = True
CHRISTMAS_EVENT_START = "2024-12-01"
CHRISTMAS_EVENT_END = "2024-12-31"
CHRISTMAS_REWARDS_MULTIPLIER = 1.5  # 50% more rewards during Christmas

# Christmas special items
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

# Christmas achievements
CHRISTMAS_ACHIEVEMENTS = [
    {"id": "christmas_adopter", "name": "🎄 فرزند کریسمس", "description": "در طول کریسمس یک گربه بخر", "reward": 500},
    {"id": "santa_helper", "name": "🎅 دستیار بابانوئل", "description": "۵ گربه را در کریسمس بخر", "reward": 1000},
    {"id": "gift_giver", "name": "🎁 بخشنده", "description": "یک گربه را در کریسمس به کدی هدیه بده", "reward": 800},
    {"id": "christmas_collector", "name": "🦌 کلکسیونر کریسمس", "description": "تمام آیتم‌های کریسمسی را جمع کن", "reward": 2000},
]

# rarity config: price & base meow/hour
RARITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "common":    {"price": 200,   "base_mph": 1.0, "emoji": "⚪️", "breeding_cost": 100},
    "rare":      {"price": 800,   "base_mph": 3.0, "emoji": "🟦", "breeding_cost": 300},
    "epic":      {"price": 2500,  "base_mph": 7.0, "emoji": "🟪", "breeding_cost": 1000},
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

# XP system
BASE_XP_PER_LEVEL = 100
XP_MULTIPLIER = 1.5

# gear shop: item_code -> stats
GEAR_ITEMS = {
    **CHRISTMAS_ITEMS,  # Add Christmas items to regular shop during event
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

# Achievements
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

# Christmas Events (replacing regular events during Christmas)
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

# Regular events (for non-Christmas season)
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

# GIF Collections
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

CUSTOM_GIFS = [
    "https://media.giphy.com/media/v6aOjy0Qo1fIA/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",
]

CHRISTMAS_GIFS = [
    "https://media.giphy.com/media/l0MYtO5qKQkPmpxX2/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",
]

# Clan config
CLAN_CREATION_COST = 5000
CLAN_MAX_MEMBERS = 50
CLAN_BONUS_PER_MEMBER = 0.02  # 2% bonus per member

# Market config
MARKET_FEE_PERCENT = 5  # 5% fee on sales
MARKET_LISTING_DURATION = 7 * 24 * 3600  # 7 days

# Breeding config
BREEDING_COOLDOWN = 24 * 3600  # 24 hours
BREEDING_SUCCESS_RATE = 0.7  # 70% chance
BREEDING_STAT_INHERITANCE = 0.6  # 60% from parents

# in-memory state
active_events: Dict[int, Dict[str, Any]] = {}
# daily_event_counter is now handled in db.py

# ========= helper functions =========

def is_christmas_season():
    """Check if current date is within Christmas season."""
    if not CHRISTMAS_EVENT_ACTIVE:
        return False
    
    try:
        today = datetime.now().date()
        start_date = datetime.strptime(CHRISTMAS_EVENT_START, "%Y-%m-%d").date()
        end_date = datetime.strptime(CHRISTMAS_EVENT_END, "%Y-%m-%d").date()
        
        return start_date <= today <= end_date
    except:
        return False

async def notify_admin_error(msg: str):
    """Notify admin about errors."""
    try:
        safe_msg = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        await bot.send_message(ADMIN_ID, f"⚠️ Error:\n<code>{safe_msg[:3000]}</code>")
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

def rarity_emoji(rarity: str) -> str:
    """Get emoji for rarity."""
    return RARITY_CONFIG.get(rarity, {}).get("emoji", "⚪️")

def choose_rarity() -> str:
    """Choose rarity based on weights."""
    roll = random.randint(1, 100)
    cur = 0
    for rarity, w in RARITY_WEIGHTS:
        cur += w
        if roll <= cur:
            return rarity
    return "common"

def xp_required_for_level(level: int) -> int:
    """Calculate XP required for a level."""
    return int(BASE_XP_PER_LEVEL * (XP_MULTIPLIER ** (level - 1)))

def parse_gear_codes(gear_field: Any) -> List[str]:
    """Parse gear codes from database field."""
    if not gear_field:
        return []
    if isinstance(gear_field, list):
        return [str(x) for x in gear_field]
    return [g.strip() for g in str(gear_field).split(",") if g.strip()]

def compute_cat_effective_stats(cat: Dict[str, Any]) -> Dict[str, Any]:
    """Compute cat's effective stats with gear bonuses."""
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
    """Calculate meow/hour for a cat."""
    rarity = cat.get("rarity", "common")
    conf = RARITY_CONFIG.get(rarity, RARITY_CONFIG["common"])
    base = float(conf["base_mph"])
    
    level = int(cat.get("level", 1))
    level_mult = 1.0 + (level - 1) * 0.1  # 10% increase per level
    
    gear_codes = parse_gear_codes(cat.get("gear", ""))
    gear_bonus = 0.0
    for code in gear_codes:
        item = GEAR_ITEMS.get(code)
        if item:
            gear_bonus += float(item.get("mph_bonus", 0.0))
    
    # Apply stat bonuses
    stats = compute_cat_effective_stats(cat)
    stat_bonus = (stats["power"] + stats["agility"] + stats["luck"]) * 0.02
    
    return base * level_mult + gear_bonus + stat_bonus

def apply_cat_tick(cat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Apply hunger & happiness decay based on elapsed time.
    Returns updated cat dict or None if cat died.
    """
    now = int(time.time())
    last_ts = cat.get("last_tick_ts") or cat.get("created_at") or now
    elapsed = max(0, now - int(last_ts))
    
    if elapsed < 60:  # Less than 1 minute, ignore
        return cat
    
    hours = elapsed / 3600.0
    
    hunger = int(cat.get("hunger", 100) - HUNGER_DECAY_PER_HOUR * hours)
    happiness = int(cat.get("happiness", 100) - HAPPINESS_DECAY_PER_HOUR * hours)
    
    # Ensure values are within bounds
    hunger = max(0, min(100, hunger))
    happiness = max(0, min(100, happiness))
    
    # Check for death
    if hunger <= 0 and elapsed > CAT_DEATH_TIMEOUT:
        return None  # Cat died
    
    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["last_tick_ts"] = now
    
    return cat

def calculate_breeding_result(parent1: Dict, parent2: Dict) -> Dict:
    """Calculate breeding result between two cats."""
    # Determine offspring rarity (can be higher than parents)
    rarities = ["common", "rare", "epic", "legendary", "mythic", "special"]
    parent1_idx = rarities.index(parent1["rarity"]) if parent1["rarity"] in rarities else 0
    parent2_idx = rarities.index(parent2["rarity"]) if parent2["rarity"] in rarities else 0
    
    # Offspring can be same or one level higher than best parent
    max_idx = max(parent1_idx, parent2_idx)
    possible_rarities = rarities[max(0, max_idx-1):min(len(rarities), max_idx+2)]
    
    offspring_rarity = random.choice(possible_rarities)
    
    # Inherit traits
    if random.random() < 0.5:
        element = parent1["element"]
    else:
        element = parent2["element"]
    
    if random.random() < 0.5:
        trait = parent1["trait"]
    else:
        trait = parent2["trait"]
    
    # Inherit stats
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
    """Calculate clan bonus based on member count."""
    return 1.0 + (member_count * CLAN_BONUS_PER_MEMBER)

async def check_and_award_achievements(user_tg: int, achievement_id: str):
    """Check and award achievements to user."""
    try:
        user_db_id = get_or_create_user(user_tg, None)
        if not user_db_id:
            return
        
        # Check if already has achievement
        user_achievements = get_user_achievements(user_db_id)
        if any(a["achievement_id"] == achievement_id for a in user_achievements):
            return
        
        # Find achievement
        all_achievements = ACHIEVEMENTS + CHRISTMAS_ACHIEVEMENTS
        achievement = next((a for a in all_achievements if a["id"] == achievement_id), None)
        if not achievement:
            return
        
        # Award achievement
        add_achievement(user_db_id, achievement_id)
        
        # Give reward
        user = get_user(user_tg)
        if user and "reward" in achievement:
            new_points = user.get("mew_points", 0) + achievement["reward"]
            update_user_mew(user_tg, mew_points=new_points)
            
            # Notify user
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
    """
    Calculate passive income from all cats and credit user.
    Returns points gained.
    """
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
    """Trigger random events in groups."""
    if message.chat.type not in ("group", "supergroup"):
        return
    
    chat_id = message.chat.id
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Get current count
    current_count = get_daily_event_count(chat_id, today)
    if current_count >= 3:
        return
    
    # Check cooldown (last event time)
    if chat_id in active_events:
        event_ts = active_events[chat_id].get("ts", 0)
        if time.time() - event_ts < 3600:  # 1 hour cooldown
            return
    
    # Random chance
    if random.random() > 0.15:  # 15% chance
        return
    
    # Choose events based on season
    if is_christmas_season():
        event = random.choice(CHRISTMAS_EVENTS)
    else:
        event = random.choice(REGULAR_EVENTS)
    
    active_events[chat_id] = {
        "event": event,
        "ts": int(time.time()),
    }
    
    # Update counter
    update_daily_event_count(chat_id, today, current_count + 1)
    
    await bot.send_message(chat_id, event["text"])

async def process_event_answer(message: types.Message) -> bool:
    """Process answers to random events."""
    chat_id = message.chat.id
    if chat_id not in active_events:
        return False
    
    event_info = active_events[chat_id]
    event = event_info["event"]
    answer = (message.text or "").strip()
    
    if answer != event["answer"]:
        return False
    
    # First correct answer wins
    del active_events[chat_id]
    
    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    
    if not user_db_id:
        await message.reply("❌ خطا در ایجاد کاربر.")
        return True
    
    reward = event["reward"]
    response_text = f"🎉 برنده‌ی رویداد: {message.from_user.full_name}\n"
    
    try:
        if reward["type"] == "points":
            user = get_user(user_tg)
            current = user.get("mew_points", 0) if user else 0
            amount = reward["amount"]
            # Apply Christmas multiplier
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
            # Add special Christmas cat
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

@dp.message_handler(commands=["start", "help"])
async def cmd_start(message: types.Message):
    """Start command handler."""
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
            text += "• ایونت‌های ویژه کریسمس در گروه‌ها\n"
            text += "• جایزه‌های ۵۰٪ بیشتر!\n\n"
        
        text += "💰 **انواع گربه:**\n"
        text += "common(200), rare(800), epic(2500), legendary(7000), mythic(15000)"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(lambda m: m.text and m.text.strip().lower() == "mew")
async def handle_mew(message: types.Message):
    """Handle mew command (text)."""
    await maybe_trigger_random_event(message)
    
    user_tg = message.from_user.id
    username = message.from_user.username
    chat_id = message.chat.id
    
    # Get or create user
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در ایجاد حساب کاربری.")
        return
    
    # Register user group
    register_user_group(user_db_id, chat_id)
    
    # Apply passive income
    passive_gained = apply_passive_income(user_tg, user_db_id)
    
    # Check cooldown
    user = get_user(user_tg)
    now = int(time.time())
    last_mew = user.get("last_mew_ts") or 0
    diff = now - last_mew
    
    if diff < MEW_COOLDOWN:
        remaining = MEW_COOLDOWN - diff
        mins = remaining // 60
        secs = remaining % 60
        
        text = f"⏳ باید {mins} دقیقه و {secs} ثانیه صبر کنی!"
        if passive_gained > 0:
            text += f"\n💤 در این مدت {passive_gained} امتیاز غیرفعال گرفتی!"
        
        await message.reply(text)
        return
    
    # Calculate mew points (1-5)
    gained = random.randint(1, 5)
    # Apply Christmas bonus
    if is_christmas_season():
        gained = int(gained * CHRISTMAS_REWARDS_MULTIPLIER)
    
    current_points = user.get("mew_points", 0)
    new_points = current_points + gained + passive_gained
    
    # Update user
    update_user_mew(
        telegram_id=user_tg,
        mew_points=new_points,
        last_mew_ts=now
    )
    
    # Send response
    text = f"😺 **میو!**\n🎁 {gained} امتیاز گرفتی!"
    if is_christmas_season():
        text += " 🎄 (بونوس کریسمس!)"
    if passive_gained > 0:
        text += f"\n💤 +{passive_gained} امتیاز غیرفعال"
    text += f"\n💰 مجموع: {new_points} امتیاز"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["profile"])
async def cmd_profile(message: types.Message):
    """Show user profile."""
    await maybe_trigger_random_event(message)
    
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در بارگذاری پروفایل.")
        return
    
    # Apply passive income
    passive_gained = apply_passive_income(user_tg, user_db_id)
    
    # Get user data
    user = get_user(user_tg)
    cats = get_user_cats(user_db_id)
    
    # Calculate stats
    total_mph = 0.0
    alive_cats = 0
    total_level = 0
    
    for cat in cats:
        updated_cat = apply_cat_tick(cat)
        if updated_cat:
            total_mph += compute_cat_mph(updated_cat)
            alive_cats += 1
            total_level += updated_cat.get("level", 1)
            # Update cat in DB
            update_cat_stats(
                cat_id=updated_cat["id"],
                owner_id=user_db_id,
                hunger=updated_cat["hunger"],
                happiness=updated_cat["happiness"],
                last_tick_ts=updated_cat["last_tick_ts"]
            )
    
    avg_level = total_level / max(1, alive_cats)
    points = user.get("mew_points", 0) if user else 0
    
    # Build profile text
    text = f"🐾 **پروفایل {message.from_user.full_name}**\n\n"
    text += f"💰 امتیاز: {points}\n"
    text += f"🐱 گربه‌ها: {alive_cats} (سطح متوسط: {avg_level:.1f})\n"
    text += f"⚡ درآمد ساعتی: {total_mph:.1f} میو/ساعت\n"
    
    if is_christmas_season():
        text += f"🎄 **ایونت کریسمس فعال است!**\n"
        text += f"🎁 جایزه‌ها ۵۰٪ بیشتر!\n"
    
    if passive_gained > 0:
        text += f"\n💤 در این بازدید {passive_gained} امتیاز غیرفعال گرفتی!"
    
    # Check clan membership
    clan_info = get_clan_info(user_db_id)
    if clan_info:
        members = get_clan_members(clan_info["id"])
        bonus = calculate_clan_bonus(len(members))
        text += f"\n👥 کلن: {clan_info['name']} (+{int((bonus - 1) * 100)}٪ بونوس)"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["leaderboard"])
async def cmd_leaderboard(message: types.Message):
    """Show leaderboard."""
    await maybe_trigger_random_event(message)
    
    rows = get_leaderboard(limit=10)
    if not rows:
        await message.reply("🏆 هنوز کسی امتیازی ندارد!")
        return
    
    text = "🏆 **لیدربورد میولند**\n\n"
    
    for i, row in enumerate(rows, 1):
        uname = row.get("username") or f"کاربر {row['telegram_id']}"
        pts = row.get("mew_points") or 0
        
        medal = ""
        if i == 1: medal = "🥇"
        elif i == 2: medal = "🥈"
        elif i == 3: medal = "🥉"
        else: medal = f"{i}."
        
        text += f"{medal} {uname} - {pts} امتیاز\n"
    
    await message.reply(text)

@dp.message_handler(commands=["adopt"])
async def cmd_adopt(message: types.Message):
    """Adopt a new cat."""
    await maybe_trigger_random_event(message)
    
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در ایجاد حساب کاربری.")
        return
    
    # Apply passive income
    apply_passive_income(user_tg, user_db_id)
    
    # Get user points
    user = get_user(user_tg)
    if not user:
        await message.reply("❌ کاربر یافت نشد.")
        return
    
    points = user.get("mew_points", 0)
    
    # Parse rarity from arguments
    args = message.get_args()
    if args:
        args = args.strip().lower()
        if args in RARITY_CONFIG:
            rarity = args
        else:
            await message.reply("❌ نوع گربه نامعتبر است!\nانواع: common, rare, epic, legendary, mythic")
            return
    else:
        rarity = choose_rarity()
    
    # Check if user can afford
    price = RARITY_CONFIG[rarity]["price"]
    # Apply Christmas discount
    if is_christmas_season():
        price = int(price * 0.9)  # 10% discount
    
    if points < price:
        await message.reply(
            f"❌ امتیاز کافی نیست!\n💰 نیاز: {price} | 💎 دارایی: {points}\n"
            f"با تایپ `mew` امتیاز جمع کن!"
        )
        return
    
    # Create cat
    element = random.choice(ELEMENTS)
    trait = random.choice(TRAITS)
    name = f"گربهٔ {rarity}"
    description = f"یک گربه‌ی {rarity} با عنصر {element} و خوی {trait}"
    
    cat_id = add_cat(user_db_id, name, rarity, element, trait, description)
    if not cat_id:
        await message.reply("❌ خطا در ایجاد گربه.")
        return
    
    # Deduct points
    update_user_mew(user_tg, mew_points=points - price)
    
    # Award first cat achievement
    if len(get_user_cats(user_db_id)) == 1:
        await check_and_award_achievements(user_tg, "first_cat")
    
    # Send success message
    text = f"🎉 **گربه جدید گرفتی!**\n\n"
    text += f"{rarity_emoji(rarity)} **{name}**\n"
    text += f"🎯 عنصر: {element}\n"
    text += f"✨ خوی: {trait}\n"
    text += f"💰 قیمت: {price} امتیاز"
    
    if is_christmas_season():
        text += " (۱۰٪ تخفیف کریسمس! 🎄)"
    
    text += f"\n📊 ID: {cat_id}\n\n"
    text += f"💎 باقی‌مانده: {points - price} امتیاز"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["cats"])
async def cmd_cats(message: types.Message):
    """List user's cats."""
    await maybe_trigger_random_event(message)
    
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در بارگذاری گربه‌ها.")
        return
    
    # Apply passive income
    apply_passive_income(user_tg, user_db_id)
    
    # Get cats
    cats = get_user_cats(user_db_id, include_dead=False)
    if not cats:
        await message.reply("😿 هنوز گربه‌ای نداری!\nاز /adopt استفاده کن.")
        return
    
    # Update and display cats
    dead_cats = 0
    cat_list = []
    
    for i, cat in enumerate(cats, 1):
        updated_cat = apply_cat_tick(cat)
        
        if not updated_cat:
            # Cat died
            kill_cat(cat["id"], user_db_id)
            dead_cats += 1
            continue
        
        # Update in database
        update_cat_stats(
            cat_id=updated_cat["id"],
            owner_id=user_db_id,
            hunger=updated_cat["hunger"],
            happiness=updated_cat["happiness"],
            last_tick_ts=updated_cat["last_tick_ts"]
        )
        
        # Format cat info
        stats = compute_cat_effective_stats(updated_cat)
        mph = compute_cat_mph(updated_cat)
        gear_codes = parse_gear_codes(updated_cat.get("gear", ""))
        gear_text = ", ".join([GEAR_ITEMS[g]["name"] for g in gear_codes if g in GEAR_ITEMS])
        
        cat_info = (
            f"{i}. {rarity_emoji(updated_cat['rarity'])} **{updated_cat['name']}** "
            f"(ID: {updated_cat['id']})\n"
            f"   🍗 گرسنگی: {updated_cat['hunger']}/100\n"
            f"   😊 خوشحالی: {updated_cat['happiness']}/100\n"
            f"   ⬆️ سطح: {updated_cat['level']} (XP: {updated_cat['xp']}/{xp_required_for_level(updated_cat['level'])})\n"
        )
        
        if gear_text:
            cat_info += f"   🛡️ تجهیزات: {gear_text}\n"
        
        cat_info += f"   💰 درآمد: {mph:.1f} میو/ساعت"
        
        cat_list.append(cat_info)
    
    # Build response
    if dead_cats:
        cat_list.append(f"\n⚰️ {dead_cats} گربه بر اثر بی‌توجهی مردند!")
    
    text = "🐱 **گربه‌های تو:**\n\n" + "\n".join(cat_list)
    
    # Split if too long
    if len(text) > 4000:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await message.reply(chunk, parse_mode=types.ParseMode.MARKDOWN)
    else:
        await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["feed"])
async def cmd_feed(message: types.Message):
    """Feed a cat."""
    await maybe_trigger_random_event(message)
    
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در بارگذاری کاربر.")
        return
    
    # Apply passive income
    apply_passive_income(user_tg, user_db_id)
    
    # Parse arguments
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/feed <id گربه> <مقدار>`")
        return
    
    try:
        cat_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await message.reply("❌ ID و مقدار باید عدد باشند!")
        return
    
    if amount <= 0:
        await message.reply("❌ مقدار باید مثبت باشد!")
        return
    if amount > 100:
        await message.reply("❌ حداکثر مقدار ۱۰۰ است!")
        return
    
    # Get user points
    user = get_user(user_tg)
    if not user:
        await message.reply("❌ کاربر یافت نشد.")
        return
    
    points = user.get("mew_points", 0)
    cost = amount * 2  # Each hunger point costs 2 mew points
    
    if points < cost:
        await message.reply(f"❌ امتیاز کافی نیست!\n💰 نیاز: {cost} | 💎 دارایی: {points}")
        return
    
    # Get cat
    cat = get_cat(cat_id, user_db_id)
    if not cat:
        await message.reply("❌ گربه یافت نشد یا مال تو نیست!")
        return
    
    # Apply tick and check if alive
    updated_cat = apply_cat_tick(cat)
    if not updated_cat:
        kill_cat(cat_id, user_db_id)
        await message.reply("😿 این گربه بر اثر گرسنگی مرده است!")
        return
    
    # Calculate new values
    new_hunger = min(100, updated_cat["hunger"] + amount)
    new_happiness = min(100, updated_cat["happiness"] + (amount // 3))
    
    # Update cat
    update_cat_stats(
        cat_id=cat_id,
        owner_id=user_db_id,
        hunger=new_hunger,
        happiness=new_happiness,
        last_tick_ts=updated_cat["last_tick_ts"]
    )
    
    # Deduct points
    update_user_mew(user_tg, mew_points=points - cost)
    
    # Send GIF
    if FEED_GIFS:
        await bot.send_animation(message.chat.id, random.choice(FEED_GIFS))
    
    # Send response
    text = (
        f"🍗 **{updated_cat['name']} غذاشو خورد!**\n\n"
        f"🍚 گرسنگی: {updated_cat['hunger']} → {new_hunger}\n"
        f"😊 خوشحالی: {updated_cat['happiness']} → {new_happiness}\n"
        f"💰 هزینه: {cost} امتیاز\n"
        f"💎 باقی‌مانده: {points - cost} امتیاز"
    )
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["play"])
async def cmd_play(message: types.Message):
    """Play with a cat."""
    await maybe_trigger_random_event(message)
    
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در بارگذاری کاربر.")
        return
    
    # Apply passive income
    apply_passive_income(user_tg, user_db_id)
    
    # Parse arguments
    args = message.get_args().split()
    if len(args) != 1:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/play <id گربه>`")
        return
    
    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("❌ ID باید عدد باشد!")
        return
    
    # Get cat
    cat = get_cat(cat_id, user_db_id)
    if not cat:
        await message.reply("❌ گربه یافت نشد یا مال تو نیست!")
        return
    
    # Apply tick and check if alive
    updated_cat = apply_cat_tick(cat)
    if not updated_cat:
        kill_cat(cat_id, user_db_id)
        await message.reply("😿 این گربه بر اثر بی‌توجهی مرده است!")
        return
    
    # Calculate gains
    happiness_gain = 15
    hunger_loss = 5
    xp_gain = 25
    
    new_happiness = min(100, updated_cat["happiness"] + happiness_gain)
    new_hunger = max(0, updated_cat["hunger"] - hunger_loss)
    new_xp = updated_cat["xp"] + xp_gain
    
    # Check level up
    new_level = updated_cat["level"]
    leveled_up = False
    
    while new_xp >= xp_required_for_level(new_level):
        new_xp -= xp_required_for_level(new_level)
        new_level += 1
        leveled_up = True
    
    # Update cat
    update_cat_stats(
        cat_id=cat_id,
        owner_id=user_db_id,
        hunger=new_hunger,
        happiness=new_happiness,
        xp=new_xp,
        level=new_level,
        last_tick_ts=updated_cat["last_tick_ts"]
    )
    
    # Send GIF
    if PLAY_GIFS:
        await bot.send_animation(message.chat.id, random.choice(PLAY_GIFS))
    
    # Build response
    text = f"🎮 **با {updated_cat['name']} بازی کردی!**\n\n"
    text += f"😊 خوشحالی: {updated_cat['happiness']} → {new_happiness}\n"
    text += f"🍗 گرسنگی: {updated_cat['hunger']} → {new_hunger}\n"
    text += f"⭐ XP: +{xp_gain} (مجموع: {new_xp})\n"
    text += f"⬆️ سطح: {updated_cat['level']} → {new_level}\n"
    
    if leveled_up:
        text += "\n🎉 **گربه‌ات سطحش بالا رفت!**\n"
        text += f"💰 درآمد ساعتی افزایش یافت!"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["rename"])
async def cmd_rename(message: types.Message):
    """Rename a cat."""
    await maybe_trigger_random_event(message)
    
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در بارگذاری کاربر.")
        return
    
    # Apply passive income
    apply_passive_income(user_tg, user_db_id)
    
    # Parse arguments
    args = message.get_args().split(maxsplit=1)
    if len(args) != 2:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/rename <id گربه> <اسم جدید>`")
        return
    
    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("❌ ID باید عدد باشد!")
        return
    
    new_name = args[1].strip()
    if len(new_name) > 32:
        await message.reply("❌ اسم نمی‌تواند بیشتر از ۳۲ حرف باشد!")
        return
    
    # Get cat and check ownership
    cat = get_cat(cat_id, user_db_id)
    if not cat:
        await message.reply("❌ گربه یافت نشد یا مال تو نیست!")
        return
    
    # Check if cat is alive
    updated_cat = apply_cat_tick(cat)
    if not updated_cat:
        kill_cat(cat_id, user_db_id)
        await message.reply("😿 این گربه مرده است!")
        return
    
    # Rename
    old_name = cat["name"]
    rename_cat(user_db_id, cat_id, new_name)
    
    await message.reply(f"✅ اسم گربه از **{old_name}** به **{new_name}** تغییر کرد!")

@dp.message_handler(commands=["train"])
async def cmd_train(message: types.Message):
    """Train a cat's stat."""
    await maybe_trigger_random_event(message)
    
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در بارگذاری کاربر.")
        return
    
    # Apply passive income
    apply_passive_income(user_tg, user_db_id)
    
    # Parse arguments
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/train <id گربه> <power/agility/luck>`")
        return
    
    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("❌ ID باید عدد باشد!")
        return
    
    stat = args[1].lower()
    if stat not in ["power", "agility", "luck"]:
        await message.reply("❌ استت نامعتبر!\nموارد مجاز: power, agility, luck")
        return
    
    # Get user points
    user = get_user(user_tg)
    if not user:
        await message.reply("❌ کاربر یافت نشد.")
        return
    
    points = user.get("mew_points", 0)
    
    # Get cat
    cat = get_cat(cat_id, user_db_id)
    if not cat:
        await message.reply("❌ گربه یافت نشد یا مال تو نیست!")
        return
    
    # Check if cat is alive
    updated_cat = apply_cat_tick(cat)
    if not updated_cat:
        kill_cat(cat_id, user_db_id)
        await message.reply("😿 این گربه مرده است!")
        return
    
    # Calculate cost
    current_stat = cat.get(f"stat_{stat}", 1)
    cost = current_stat * 100
    
    if points < cost:
        await message.reply(f"❌ امتیاز کافی نیست!\n💰 نیاز: {cost} | 💎 دارایی: {points}")
        return
    
    # Update stat
    new_stat = current_stat + 1
    update_data = {f"stat_{stat}": new_stat}
    update_cat_stats(cat_id, user_db_id, **update_data)
    
    # Deduct points
    update_user_mew(user_tg, mew_points=points - cost)
    
    # Send response
    text = (
        f"🏋️ **{cat['name']} آموزش دید!**\n\n"
        f"📈 {stat}: {current_stat} → {new_stat}\n"
        f"💰 هزینه: {cost} امتیاز\n"
        f"💎 باقی‌مانده: {points - cost} امتیاز"
    )
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["shop"])
async def cmd_shop(message: types.Message):
    """Show shop items."""
    await maybe_trigger_random_event(message)
    
    text = "🛒 **فروشگاه تجهیزات گربه**\n\n"
    
    # Regular items
    text += "📦 **تجهیزات معمولی:**\n"
    for code, item in GEAR_ITEMS.items():
        if not item.get("seasonal", False):
            text += (
                f"• {item['name']} (کد: `{code}`)\n"
                f"  قیمت: {item['price']} 💎 | نیاز به لول: {item['min_level']}+\n"
                f"  بونوس: +{item['mph_bonus']} میو/ساعت | قدرت: +{item['power_bonus']} | چابکی: +{item['agility_bonus']} | شانس: +{item['luck_bonus']}\n\n"
            )
    
    # Christmas items (only show during Christmas)
    if is_christmas_season():
        text += "🎄 **تجهیزات کریسمسی:**\n"
        for code, item in GEAR_ITEMS.items():
            if item.get("seasonal", False):
                text += (
                    f"• {item['name']} (کد: `{code}`)\n"
                    f"  قیمت: {item['price']} 💎 | نیاز به لول: {item['min_level']}+\n"
                    f"  بونوس: +{item['mph_bonus']} میو/ساعت | قدرت: +{item['power_bonus']} | چابکی: +{item['agility_bonus']} | شانس: +{item['luck_bonus']}\n\n"
                )
    
    text += "برای خرید: `/buygear <id_گربه> <کد_آیتم>`"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["buygear"])
async def cmd_buygear(message: types.Message):
    """Buy gear for a cat."""
    await maybe_trigger_random_event(message)
    
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/buygear <id گربه> <کد آیتم>`")
        return
    
    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("❌ ID باید عدد باشد!")
        return
    
    code = args[1].lower()
    if code not in GEAR_ITEMS:
        await message.reply("❌ کد آیتم نامعتبر است. `/shop` را چک کن.")
        return
    
    item = GEAR_ITEMS[code]
    
    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    
    # Apply passive income
    apply_passive_income(user_tg, user_db_id)
    
    # Get cat
    cat = get_cat(cat_id, user_db_id)
    if not cat:
        await message.reply("❌ گربه یافت نشد یا مال تو نیست!")
        return
    
    # Check level requirement
    if cat["level"] < item["min_level"]:
        await message.reply(
            f"❌ برای خرید {item['name']}، گربه باید حداقل لول {item['min_level']} باشد.\n"
            f"لول فعلی: {cat['level']}"
        )
        return
    
    # Get user points
    user = get_user(user_tg)
    if not user:
        await message.reply("❌ کاربر یافت نشد.")
        return
    
    points = user.get("mew_points", 0)
    price = item["price"]
    
    # Apply Christmas discount
    if is_christmas_season() and item.get("seasonal", False):
        price = int(price * 0.8)  # 20% discount for Christmas items
    
    if points < price:
        await message.reply(f"❌ امتیاز کافی نیست!\n💰 نیاز: {price} | 💎 دارایی: {points}")
        return
    
    # Check if already has this gear
    gear_codes = parse_gear_codes(cat.get("gear", ""))
    if code in gear_codes:
        await message.reply(f"❌ این آیتم قبلاً روی {cat['name']} نصب شده!")
        return
    
    # Add gear
    gear_codes.append(code)
    new_gear_str = ",".join(gear_codes)
    
    update_cat_stats(cat_id, user_db_id, gear=new_gear_str)
    update_user_mew(user_tg, mew_points=points - price)
    
    # Calculate new MPH
    updated_cat = {**cat, "gear": new_gear_str}
    mph = compute_cat_mph(updated_cat)
    
    text = f"🎉 **{item['name']} روی {cat['name']} نصب شد!**\n\n"
    text += f"💰 قیمت: {price} امتیاز"
    
    if is_christmas_season() and item.get("seasonal", False):
        text += " (۲۰٪ تخفیف کریسمس! 🎄)"
    
    text += f"\n💎 باقی‌مانده: {points - price} امتیاز\n"
    text += f"⚡ درآمد جدید: {mph:.1f} میو/ساعت"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["fight"])
async def cmd_fight(message: types.Message):
    """Fight between two cats."""
    await maybe_trigger_random_event(message)
    
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/fight <id_گربه_تو> <id_گربه_حریف>`")
        return
    
    try:
        my_id = int(args[0])
        enemy_id = int(args[1])
    except ValueError:
        await message.reply("❌ ID ها باید عدد باشند!")
        return
    
    user_tg = message.from_user.id
    username = message.from_user.username
    my_db_id = get_or_create_user(user_tg, username)
    
    # Apply passive income
    apply_passive_income(user_tg, my_db_id)
    
    # Get my cat
    my_cat = get_cat(my_id, my_db_id)
    if not my_cat:
        await message.reply("❌ گربه اول مال تو نیست یا وجود ندارد!")
        return
    
    # Get enemy cat (can be anyone's)
    enemy_cat = get_cat(enemy_id)
    if not enemy_cat:
        await message.reply("❌ گربه دوم وجود ندارد!")
        return
    
    # Check level requirement
    if my_cat["level"] < 9 or enemy_cat["level"] < 9:
        await message.reply("❌ برای جنگ، هر دو گربه باید حداقل لول ۹ باشند!")
        return
    
    # Calculate battle
    my_stats = compute_cat_effective_stats(my_cat)
    enemy_stats = compute_cat_effective_stats(enemy_cat)
    
    my_score = 0
    enemy_score = 0
    battle_log = []
    
    for round_num in range(1, 4):
        my_roll = (
            my_stats["power"] * random.uniform(0.8, 1.2) +
            my_stats["agility"] * random.uniform(0.5, 1.0) +
            my_stats["luck"] * random.uniform(0.0, 0.5)
        )
        
        enemy_roll = (
            enemy_stats["power"] * random.uniform(0.8, 1.2) +
            enemy_stats["agility"] * random.uniform(0.5, 1.0) +
            enemy_stats["luck"] * random.uniform(0.0, 0.5)
        )
        
        if my_roll > enemy_roll:
            my_score += 1
            battle_log.append(f"راند {round_num}: ✅ بردی")
        elif enemy_roll > my_roll:
            enemy_score += 1
            battle_log.append(f"راند {round_num}: ❌ باختی")
        else:
            battle_log.append(f"راند {round_num}: ⚖️ مساوی")
    
    # Determine result
    if my_score > enemy_score:
        result = "🏆 **بردی!**"
        xp_gain = 50
        point_gain = 100
        
        # Apply Christmas bonus
        if is_christmas_season():
            xp_gain = int(xp_gain * CHRISTMAS_REWARDS_MULTIPLIER)
            point_gain = int(point_gain * CHRISTMAS_REWARDS_MULTIPLIER)
        
        # Update cat
        new_xp = my_cat["xp"] + xp_gain
        new_level = my_cat["level"]
        
        while new_xp >= xp_required_for_level(new_level):
            new_xp -= xp_required_for_level(new_level)
            new_level += 1
        
        update_cat_stats(
            my_id,
            my_db_id,
            xp=new_xp,
            level=new_level,
            happiness=min(100, my_cat["happiness"] + 20)
        )
        
        # Give points
        user = get_user(user_tg)
        if user:
            new_points = user.get("mew_points", 0) + point_gain
            update_user_mew(user_tg, mew_points=new_points)
        
        result += f"\n🎁 {xp_gain} XP + {point_gain} امتیاز گرفتی!"
        
        # Check for level up
        if new_level > my_cat["level"]:
            result += f"\n🎉 گربه‌ات به لول {new_level} رسید!"
    
    elif enemy_score > my_score:
        result = "😿 **باختی!**"
        # Lose some happiness
        update_cat_stats(
            my_id,
            my_db_id,
            happiness=max(0, my_cat["happiness"] - 10)
        )
        result += "\nگربه‌ات ۱۰ خوشحالی از دست داد!"
    
    else:
        result = "🤝 **مساوی شد!**"
        # Small XP gain for tie
        update_cat_stats(
            my_id,
            my_db_id,
            xp=my_cat["xp"] + 10
        )
        result += "\n۱۰ XP گرفتی!"
    
    # Build battle report
    text = f"⚔️ **نبرد: {my_cat['name']} 🆚 {enemy_cat['name']}**\n\n"
    text += "\n".join(battle_log)
    text += f"\n\n**نتیجه:** {my_score} - {enemy_score}\n"
    text += result
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

@dp.message_handler(commands=["transfer"])
async def cmd_transfer(message: types.Message):
    """Transfer a cat to another user."""
    await maybe_trigger_random_event(message)
    
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/transfer <id_گربه> @username`")
        return
    
    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("❌ ID باید عدد باشد!")
        return
    
    target_username = args[1].lstrip("@").strip()
    if not target_username:
        await message.reply("❌ یوزرنیم نامعتبر است!")
        return
    
    user_tg = message.from_user.id
    username = message.from_user.username
    from_db_id = get_or_create_user(user_tg, username)
    
    # Apply passive income
    apply_passive_income(user_tg, from_db_id)
    
    # Check cat ownership
    cat = get_cat(cat_id, from_db_id)
    if not cat:
        await message.reply("❌ گربه یافت نشد یا مال تو نیست!")
        return
    
    # Find target user
    all_users = get_all_users()
    target_user = None
    
    for u in all_users:
        if (u.get("username") or "").lower() == target_username.lower():
            target_user = u
            break
    
    if not target_user:
        await message.reply(
            "❌ کاربر هدف پیدا نشد!\n"
            "مطمئن شو کاربر با بات /start کرده و یوزرنیم صحیح را وارد کرده‌ای."
        )
        return
    
    # Transfer cat
    success = set_cat_owner(cat_id, target_user["id"])
    
    if success:
        text = f"✅ **{cat['name']} به @{target_username} منتقل شد!**\n\n"
        text += f"📦 ID گربه: {cat_id}\n"
        text += f"🎯 نوع: {cat['rarity']}\n"
        text += f"👋 دیگر مالک این گربه نیستی."
        
        # If Christmas and transferring to someone, award achievement
        if is_christmas_season():
            await check_and_award_achievements(user_tg, "gift_giver")
    else:
        text = "❌ خطا در انتقال گربه!"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

# ========= NEW FEATURE: Breeding System =========

@dp.message_handler(commands=["breed"])
async def cmd_breed(message: types.Message, state: FSMContext):
    """Start breeding process."""
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در بارگذاری کاربر.")
        return
    
    # Parse arguments
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/breed <id_گربه_اول> <id_گربه_دوم>`")
        return
    
    try:
        cat1_id = int(args[0])
        cat2_id = int(args[1])
    except ValueError:
        await message.reply("❌ ID ها باید عدد باشند!")
        return
    
    # Get cats
    cat1 = get_cat(cat1_id, user_db_id)
    cat2 = get_cat(cat2_id, user_db_id)
    
    if not cat1 or not cat2:
        await message.reply("❌ یکی از گربه‌ها پیدا نشد یا مال تو نیست!")
        return
    
    # Check if cats are alive
    cat1 = apply_cat_tick(cat1)
    cat2 = apply_cat_tick(cat2)
    
    if not cat1 or not cat2:
        await message.reply("😿 یکی از گربه‌ها مرده است!")
        return
    
    # Check breeding cooldown
    now = time.time()
    last_breed1 = cat1.get("last_breed_ts", 0)
    last_breed2 = cat2.get("last_breed_ts", 0)
    
    if now - last_breed1 < BREEDING_COOLDOWN:
        remaining = BREEDING_COOLDOWN - (now - last_breed1)
        hours = int(remaining // 3600)
        await message.reply(f"⏳ گربه اول باید {hours} ساعت دیگر استراحت کند!")
        return
    
    if now - last_breed2 < BREEDING_COOLDOWN:
        remaining = BREEDING_COOLDOWN - (now - last_breed2)
        hours = int(remaining // 3600)
        await message.reply(f"⏳ گربه دوم باید {hours} ساعت دیگر استراحت کند!")
        return
    
    # Check breeding cost
    rarity1 = cat1["rarity"]
    rarity2 = cat2["rarity"]
    cost1 = RARITY_CONFIG[rarity1]["breeding_cost"]
    cost2 = RARITY_CONFIG[rarity2]["breeding_cost"]
    total_cost = (cost1 + cost2) // 2
    
    user = get_user(user_tg)
    points = user.get("mew_points", 0)
    
    if points < total_cost:
        await message.reply(f"❌ امتیاز کافی نیست!\n💰 نیاز: {total_cost} | 💎 دارایی: {points}")
        return
    
    # Calculate result
    result = calculate_breeding_result(cat1, cat2)
    
    # Store in state
    await state.update_data(
        cat1_id=cat1_id,
        cat2_id=cat2_id,
        cat1_rarity=rarity1,
        cat2_rarity=rarity2,
        breeding_cost=total_cost,
        offspring_data=result,
        user_points=points,
        user_db_id=user_db_id
    )
    
    # Show confirmation
    text = f"🧬 **جفت‌گیری گربه‌ها**\n\n"
    text += f"🐱 {cat1['name']} ({rarity_emoji(rarity1)} {rarity1})\n"
    text += f"🐱 {cat2['name']} ({rarity_emoji(rarity2)} {rarity2})\n\n"
    text += f"🧪 نتیجه احتمالی: {rarity_emoji(result['rarity'])} {result['rarity']}\n"
    text += f"🎯 عنصر: {result['element']}\n"
    text += f"✨ خوی: {result['trait']}\n"
    text += f"💰 هزینه: {total_cost} میوپوینت\n\n"
    text += "آیا می‌خواهید ادامه دهید؟ (بله/خیر)"
    
    await message.reply(text)
    await BreedStates.confirm_breeding.set()

@dp.message_handler(state=BreedStates.confirm_breeding)
async def process_breeding_confirmation(message: types.Message, state: FSMContext):
    """Process breeding confirmation."""
    if message.text.lower() not in ["بله", "yes", "y", "✅"]:
        await message.reply("❌ جفت‌گیری لغو شد.")
        await state.finish()
        return
    
    data = await state.get_data()
    
    user_tg = message.from_user.id
    user_db_id = data["user_db_id"]
    
    # Deduct points
    update_user_mew(user_tg, mew_points=data["user_points"] - data["breeding_cost"])
    
    # Check breeding success
    if random.random() > BREEDING_SUCCESS_RATE:
        await message.reply("😿 متأسفانه جفت‌گیری موفقیت‌آمیز نبود. گربه‌ها باید استراحت کنند.")
        
        # Update breed timestamps anyway
        now = int(time.time())
        update_cat_stats(data["cat1_id"], user_db_id, last_breed_ts=now)
        update_cat_stats(data["cat2_id"], user_db_id, last_breed_ts=now)
        
        await state.finish()
        return
    
    # Create offspring
    offspring_data = data["offspring_data"]
    offspring_name = f"{offspring_data['rarity'].title()} Breed"
    
    cat_id = add_cat(
        user_db_id,
        offspring_name,
        offspring_data["rarity"],
        offspring_data["element"],
        offspring_data["trait"],
        f"فرزند {offspring_data['rarity']} حاصل از جفت‌گیری"
    )
    
    # Apply inherited stats and record breeding
    if cat_id:
        update_cat_stats(cat_id, user_db_id, **offspring_data["stats"])
        breed_cats(data["cat1_id"], data["cat2_id"], cat_id, True)
    
    # Update parent breed timestamps
    now = int(time.time())
    update_cat_stats(data["cat1_id"], user_db_id, last_breed_ts=now)
    update_cat_stats(data["cat2_id"], user_db_id, last_breed_ts=now)
    
    # Award achievement
    await check_and_award_achievements(user_tg, "breeder")
    
    # Send result
    text = f"🎉 **جفت‌گیری موفقیت‌آمیز بود!**\n\n"
    text += f"🐣 گربه جدید متولد شد!\n"
    text += f"{rarity_emoji(offspring_data['rarity'])} **{offspring_name}**\n"
    text += f"🎯 عنصر: {offspring_data['element']}\n"
    text += f"✨ خوی: {offspring_data['trait']}\n"
    text += f"💰 هزینه: {data['breeding_cost']} میوپوینت\n"
    text += f"📊 ID گربه جدید: {cat_id}"
    
    await message.reply(text)
    await state.finish()

# ========= NEW FEATURE: Achievements System =========

@dp.message_handler(commands=["achievements"])
async def cmd_achievements(message: types.Message):
    """Show user achievements."""
    user_tg = message.from_user.id
    username = message.from_user.username
    
    user_db_id = get_or_create_user(user_tg, username)
    if not user_db_id:
        await message.reply("❌ خطا در بارگذاری کاربر.")
        return
    
    user_achievements = get_user_achievements(user_db_id)
    
    # Get all achievements
    all_achievements = ACHIEVEMENTS.copy()
    if is_christmas_season():
        all_achievements.extend(CHRISTMAS_ACHIEVEMENTS)
    
    # Build achievements list
    unlocked = []
    locked = []
    
    for achievement in all_achievements:
        achieved = any(a["achievement_id"] == achievement["id"] for a in user_achievements)
        
        achievement_info = {
            "name": achievement["name"],
            "description": achievement["description"],
            "reward": achievement.get("reward", 0),
            "unlocked": achieved
        }
        
        if achieved:
            unlocked.append(achievement_info)
        else:
            locked.append(achievement_info)
    
    # Format response
    text = "🏆 **دستاوردهای شما**\n\n"
    
    if unlocked:
        text += "✅ **دستاوردهای باز شده:**\n"
        for ach in unlocked:
            text += f"• {ach['name']}: {ach['description']} (+{ach['reward']} امتیاز)\n"
        text += "\n"
    
    if locked:
        text += "🔒 **دستاوردهای قفل شده:**\n"
        for ach in locked:
            text += f"• {ach['name']}: {ach['description']}\n"
    
    total_rewards = sum(ach.get("reward", 0) for ach in unlocked)
    text += f"\n💰 **مجموع جایزه‌های دریافتی:** {total_rewards} میوپوینت"
    
    await message.reply(text)

# ========= NEW FEATURE: Clan System =========

@dp.message_handler(commands=["clan"])
async def cmd_clan(message: types.Message):
    """Clan system main command."""
    args = message.get_args().split()
    
    if not args:
        # Show clan info if user is in one
        user_tg = message.from_user.id
        user_db_id = get_or_create_user(user_tg, message.from_user.username)
        
        clan_info = get_clan_info(user_db_id)
        if clan_info:
            await show_clan_info(message, clan_info)
        else:
            await message.reply(
                "👥 **سیستم کلن**\n\n"
                "دستورات:\n"
                "/clan create <نام> - ایجاد کلن جدید (هزینه: ۵۰۰۰ امتیاز)\n"
                "/clan join <نام> - پیوستن به کلن\n"
                "/clan leave - ترک کلن\n"
                "/clan members - مشاهده اعضا\n"
                "/clan bonus - مشاهده بونوس کلن"
            )
        return
    
    subcommand = args[0].lower()
    
    if subcommand == "create":
        await cmd_clan_create(message, args[1:])
    elif subcommand == "join":
        await cmd_clan_join(message, args[1:])
    elif subcommand == "leave":
        await cmd_clan_leave(message)
    elif subcommand == "members":
        await cmd_clan_members(message)
    elif subcommand == "bonus":
        await cmd_clan_bonus(message)
    elif subcommand == "info":
        await cmd_clan_info(message)

async def cmd_clan_create(message: types.Message, args: List[str]):
    """Create a new clan."""
    if len(args) < 1:
        await message.reply("❌ لطفا نام کلن را وارد کنید: `/clan create <نام>`")
        return
    
    clan_name = " ".join(args).strip()
    if len(clan_name) < 3 or len(clan_name) > 32:
        await message.reply("❌ نام کلن باید بین ۳ تا ۳۲ حرف باشد.")
        return
    
    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    
    # Check cost
    user = get_user(user_tg)
    points = user.get("mew_points", 0)
    
    if points < CLAN_CREATION_COST:
        await message.reply(f"❌ امتیاز کافی نیست!\n💰 نیاز: {CLAN_CREATION_COST} | 💎 دارایی: {points}")
        return
    
    # Create clan
    success = create_clan(user_db_id, clan_name, CLAN_CREATION_COST)
    
    if success:
        # Deduct points
        update_user_mew(user_tg, mew_points=points - CLAN_CREATION_COST)
        
        # Award achievement
        await check_and_award_achievements(user_tg, "clan_leader")
        
        await message.reply(
            f"🎉 **کلن {clan_name} با موفقیت ایجاد شد!**\n\n"
            f"💰 هزینه: {CLAN_CREATION_COST} میوپوینت\n"
            f"👑 شما رهبر کلن هستید\n"
            f"📊 از بونوس کلن بهره‌مند شوید!"
        )
    else:
        await message.reply("❌ خطا در ایجاد کلن. ممکن است نام تکراری باشد یا شما قبلاً در کلنی هستید.")

async def cmd_clan_join(message: types.Message, args: List[str]):
    """Join an existing clan."""
    if len(args) < 1:
        await message.reply("❌ لطفا نام کلن را وارد کنید: `/clan join <نام>`")
        return
    
    clan_name = " ".join(args).strip()
    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    
    success = join_clan(user_db_id, clan_name)
    
    if success:
        await message.reply(f"✅ شما با موفقیت به کلن **{clan_name}** پیوستید!")
    else:
        await message.reply("❌ خطا در پیوستن به کلن. ممکن است کلن پر باشد یا شما در کلن دیگری باشید.")

async def show_clan_info(message: types.Message, clan_info: Dict):
    """Show clan information."""
    members = get_clan_members(clan_info["id"])
    bonus = calculate_clan_bonus(len(members))
    
    text = f"👥 **کلن {clan_info['name']}**\n\n"
    text += f"👑 رهبر: {clan_info['leader_username'] or 'نامشخص'}\n"
    text += f"👥 اعضا: {len(members)}/{CLAN_MAX_MEMBERS}\n"
    text += f"📅 ایجاد: {datetime.fromtimestamp(clan_info['created_at']).strftime('%Y-%m-%d')}\n"
    text += f"🎯 بونوس: {int((bonus - 1) * 100)}٪ افزایش درآمد\n\n"
    
    # Top 5 members
    text += "🏆 برترین اعضا:\n"
    for i, member in enumerate(members[:5], 1):
        text += f"{i}. {member['username'] or 'کاربر'} - {member['mew_points']} امتیاز\n"
    
    await message.reply(text)

async def cmd_clan_leave(message: types.Message):
    """Leave current clan."""
    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    
    # Check if user is in a clan
    clan_info = get_clan_info(user_db_id)
    if not clan_info:
        await message.reply("❌ شما در هیچ کلنی نیستید!")
        return
    
    # Check if user is leader
    if clan_info["leader_id"] == user_db_id:
        await message.reply("❌ شما رهبر کلن هستید! ابتدا باید کلن را منحل کنید یا رهبری را انتقال دهید.")
        return
    
    # Leave clan (simple delete)
    # Note: This requires a delete function in db.py
    await message.reply("❌ این قابلیت در حال توسعه است!")

# ========= NEW FEATURE: Marketplace =========

@dp.message_handler(commands=["market"])
async def cmd_market(message: types.Message):
    """Marketplace main command."""
    args = message.get_args().split()
    
    if not args:
        await message.reply(
            "🏪 **بازار گربه‌ها**\n\n"
            "دستورات:\n"
            "/market list <id_گربه> <قیمت> - فروش گربه\n"
            "/market browse - مشاهده لیست گربه‌ها\n"
            "/market buy <id_آگهی> - خرید گربه\n"
            "/market my - آگهی‌های من\n"
            "/market cancel <id_آگهی> - لغو آگهی"
        )
        return
    
    subcommand = args[0].lower()
    
    if subcommand == "list":
        await cmd_market_list(message, args[1:])
    elif subcommand == "browse":
        await cmd_market_browse(message)
    elif subcommand == "buy":
        await cmd_market_buy(message, args[1:])
    elif subcommand == "my":
        await cmd_market_my(message)
    elif subcommand == "cancel":
        await cmd_market_cancel(message, args[1:])

async def cmd_market_list(message: types.Message, args: List[str]):
    """List a cat for sale."""
    if len(args) < 2:
        await message.reply("❌ فرمت اشتباه!\nاستفاده: `/market list <id_گربه> <قیمت>`")
        return
    
    try:
        cat_id = int(args[0])
        price = int(args[1])
    except ValueError:
        await message.reply("❌ ID و قیمت باید عدد باشند!")
        return
    
    if price < 100:
        await message.reply("❌ حداقل قیمت ۱۰۰ میوپوینت است!")
        return
    
    user_tg = message.from_user.id
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    
    # Check cat ownership
    cat = get_cat(cat_id, user_db_id)
    if not cat:
        await message.reply("❌ گربه پیدا نشد یا مال تو نیست!")
        return
    
    # Check if cat is alive
    updated_cat = apply_cat_tick(cat)
    if not updated_cat:
        await message.reply("😿 این گربه مرده است و قابل فروش نیست!")
        return
    
    # Create listing
    fee = int(price * MARKET_FEE_PERCENT / 100)
    expires_at = int(time.time()) + MARKET_LISTING_DURATION
    
    listing_id = create_market_listing(
        cat_id=cat_id,
        seller_id=user_db_id,
        price=price,
        fee=fee,
        expires_at=expires_at
    )
    
    if listing_id:
        await message.reply(
            f"🏪 **آگهی فروش ثبت شد!**\n\n"
            f"🐱 گربه: {cat['name']}\n"
            f"💰 قیمت: {price} میوپوینت\n"
            f"💸 کارمزد: {fee} میوپوینت ({MARKET_FEE_PERCENT}٪)\n"
            f"📊 کد آگهی: {listing_id}\n"
            f"⏰ انقضا: ۷ روز دیگر\n\n"
            f"برای خرید: `/market buy {listing_id}`"
        )
        
        # Award achievement
        await check_and_award_achievements(user_tg, "market_king")
    else:
        await message.reply("❌ خطا در ثبت آگهی. ممکن است گربه قبلاً برای فروش ثبت شده باشد.")

async def cmd_market_browse(message: types.Message):
    """Browse marketplace listings."""
    listings = get_market_listings(limit=20)
    
    if not listings:
        await message.reply("🏪 در حال حاضر هیچ گربه‌ای برای فروش وجود ندارد.")
        return
    
    text = "🏪 **گربه‌های موجود در بازار:**\n\n"
    
    for listing in listings:
        cat = get_cat(listing["cat_id"])
        if not cat:
            continue
        
        time_left = listing["expires_at"] - int(time.time())
        days = time_left // (24 * 3600)
        hours = (time_left % (24 * 3600)) // 3600
        
        text += (
            f"📊 کد: {listing['id']}\n"
            f"🐱 {cat['name']} ({rarity_emoji(cat['rarity'])} {cat['rarity']})\n"
            f"💰 قیمت: {listing['price']} میوپوینت\n"
            f"⏰ باقی‌مانده: {days} روز و {hours} ساعت\n"
            f"────────────────────\n"
        )
    
    text += "\nبرای خرید: `/market buy <کد_آگهی>`"
    
    # Split if too long
    if len(text) > 4000:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await message.reply(chunk)
    else:
        await message.reply(text)

async def cmd_market_buy(message: types.Message, args: List[str]):
    """Buy a cat from marketplace."""
    if len(args) < 1:
        await message.reply("❌ لطفا کد آگهی را وارد کنید: `/market buy <کد_آگهی>`")
        return
    
    try:
        listing_id = int(args[0])
    except ValueError:
        await message.reply("❌ کد آگهی باید عدد باشد!")
        return
    
    user_tg = message.from_user.id
    username = message.from_user.username
    buyer_db_id = get_or_create_user(user_tg, username)
    
    # Check if buyer is not the seller
    listing = next((l for l in get_market_listings() if l["id"] == listing_id), None)
    if not listing:
        await message.reply("❌ آگهی پیدا نشد!")
        return
    
    if listing["seller_id"] == buyer_db_id:
        await message.reply("❌ نمی‌توانید گربه خود را بخرید!")
        return
    
    # Check buyer's points
    buyer = get_user(user_tg)
    buyer_points = buyer.get("mew_points", 0)
    total_cost = listing["price"] + listing["fee"]
    
    if buyer_points < total_cost:
        await message.reply(f"❌ امتیاز کافی نیست!\n💰 نیاز: {total_cost} | 💎 دارایی: {buyer_points}")
        return
    
    # Process purchase
    success = buy_market_listing(listing_id, buyer_db_id)
    
    if success:
        # Transfer points
        seller_user = get_user_by_db_id(listing["seller_id"])
        if seller_user:
            seller_points = seller_user.get("mew_points", 0)
            update_user_mew(seller_user["telegram_id"], mew_points=seller_points + listing["price"])
        
        # Deduct from buyer
        update_user_mew(user_tg, mew_points=buyer_points - total_cost)
        
        # Get cat info
        cat = get_cat(listing["cat_id"])
        
        await message.reply(
            f"🎉 **خرید موفقیت‌آمیز بود!**\n\n"
            f"🐱 گربه: {cat['name']}\n"
            f"💰 قیمت پرداخت شده: {total_cost} میوپوینت\n"
            f"(قیمت: {listing['price']} + کارمزد: {listing['fee']})\n\n"
            f"گربه جدید اکنون در لیست گربه‌های شماست! 🎉"
        )
    else:
        await message.reply("❌ خطا در خرید. ممکن است آگهی منقضی شده باشد.")

# ========= NEW FEATURE: Special Cats =========

@dp.message_handler(commands=["specialcats"])
async def cmd_special_cats(message: types.Message):
    """Show available special cats."""
    user_tg = message.from_user.id
    user_db_id = get_or_create_user(user_tg, message.from_user.username)
    
    special_cats = get_special_cats(user_db_id)
    
    if not special_cats:
        await message.reply(
            "🌟 **گربه‌های ویژه**\n\n"
            "گربه‌های ویژه دارای توانایی‌های منحصر به فرد هستند!\n\n"
            "روش‌های کسب:\n"
            "• برنده شدن در ایونت‌های ویژه\n"
            "• جفت‌گیری گربه‌های افسانه‌ای\n"
            "• خرید از فروشگاه خاص در ایونت‌ها\n\n"
            "در حال حاضر هیچ گربه ویژه‌ای ندارید."
        )
        return
    
    text = "🌟 **گربه‌های ویژه شما:**\n\n"
    
    for cat in special_cats:
        ability = cat.get("special_ability", "قدرت ویژه")
        text += (
            f"{rarity_emoji(cat['rarity'])} **{cat['name']}**\n"
            f"🎯 توانایی: {ability}\n"
            f"🍗 گرسنگی: {cat['hunger']}/100\n"
            f"😊 خوشحالی: {cat['happiness']}/100\n"
            f"────────────────────\n"
        )
    
    await message.reply(text)

# ========= Catch All Handler =========

@dp.message_handler()
async def catch_all(message: types.Message):
    """Catch all messages for event processing."""
    handled = await process_event_answer(message)
    if not handled:
        # Trigger random events
        await maybe_trigger_random_event(message)

# ========= Webhook Server with FIX =========

async def handle_root(request: web.Request):
    return web.Response(text="🎄 Mewland Christmas Bot is running! 🐱")

async def handle_webhook(request: web.Request):
    """Handle webhook requests with fix for bot instance."""
    token = request.match_info.get("token")
    if token != BOT_TOKEN:
        return web.Response(status=403, text="Forbidden")
    
    logger.info("Webhook received")
    
    try:
        data = await request.json()
        
        # IMPORTANT FIX: Create Update object properly
        from aiogram.types import Update
        update = Update(**data)
        
        # FIX: Set the current bot instance for this update
        from aiogram import Bot
        Bot.set_current(bot)
        
        # Process the update
        await dp.process_update(update)
        
    except Exception as e:
        logger.exception(f"Error processing update: {e}")
        await notify_admin_error(f"Webhook error: {str(e)}")
    
    return web.Response(text="OK")

async def on_startup(app: web.Application):
    """Startup tasks."""
    logger.info("🎅 Starting Mewland Christmas Bot...")
    
    # Delete old webhook
    try:
        await bot.delete_webhook()
        logger.info("Old webhook deleted")
    except Exception as e:
        logger.warning(f"Could not delete webhook: {e}")
    
    # Set new webhook
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set to: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        raise
    
    # Initialize database
    init_db()
    logger.info("Database initialized")
    
    # Check Christmas season
    if is_christmas_season():
        logger.info("🎄 Christmas event is ACTIVE!")
    
    # Notify admin
    try:
        await bot.send_message(ADMIN_ID, "🤖 Mewland Christmas Bot started successfully!")
        if is_christmas_season():
            await bot.send_message(ADMIN_ID, "🎄 Christmas event is ACTIVE! 🎅")
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

def main():
    """Main application entry point."""
    app = web.Application()
    
    # Add routes
    app.router.add_get("/", handle_root)
    app.router.add_post("/webhook/{token}", handle_webhook)
    
    # Add startup tasks
    app.on_startup.append(on_startup)
    
    # Run app
    logger.info(f"Starting server on {APP_HOST}:{APP_PORT}")
    web.run_app(app, host=APP_HOST, port=APP_PORT)

if __name__ == "__main__":
    main()
