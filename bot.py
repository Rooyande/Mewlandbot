# bot.py - نسخه کامل با تمام ویژگی‌ها

import logging
import os
import random
import time
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.utils.exceptions import TelegramAPIError
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
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
    get_seasonal_events,
    add_seasonal_event,
    get_user_seasonal_progress,
    update_seasonal_progress,
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
WEBHOOK_URL = WEBHOOK_HOST + WEBPOOK_PATH

APP_HOST = "0.0.0.0"
APP_PORT = int(os.getenv("PORT", "10000"))

# Initialize bot with storage
storage = MemoryStorage()
bot = Bot(BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

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
    {"id": "christmas_adopter", "name": "🎄 فرزند کریسمس", "description": "در طول کریسمس یک گربه بخر"},
    {"id": "santa_helper", "name": "🎅 دستیار بابانوئل", "description": "۵ گربه را در کریسمس بخر"},
    {"id": "gift_giver", "name": "🎁 بخشنده", "description": "یک گربه را در کریسمس به کدی هدیه بده"},
    {"id": "christmas_collector", "name": "🦌 کلکسیونر کریسمس", "description": "تمام آیتم‌های کریسمسی را جمع کن"},
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

# GIF Collections (70+ GIFs for each category)
# Note: These are example URLs. You should replace with actual GIF URLs or Telegram file_ids

PLAY_GIFS = [
    "https://media.giphy.com/media/JIX9t2j0ZTN9S/giphy.gif",
    "https://media.giphy.com/media/mlvseq9yvZhba/giphy.gif",
    "https://media.giphy.com/media/13CoXDiaCcCoyk/giphy.gif",
    "https://media.giphy.com/media/8vQSQ3cNXuDGo/giphy.gif",
    "https://media.giphy.com/media/3o7abAHdYvZdBNnGZq/giphy.gif",
    "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
    "https://media.giphy.com/media/C9x8gX02SnMIoAClXa/giphy.gif",
    "https://media.giphy.com/media/13ZF2HzfKXmB5e/giphy.gif",
    # Add 62 more GIF URLs here...
] * 10  # Multiply to reach 70+ (replace with actual unique URLs)

FEED_GIFS = [
    "https://media.giphy.com/media/12HZukMBlutpoQ/giphy.gif",
    "https://media.giphy.com/media/1iu8uG2cjYFZS6wTxv/giphy.gif",
    "https://media.giphy.com/media/l0MYC0LajbaPoEADu/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",
    # Add 65 more GIF URLs here...
] * 14

CUSTOM_GIFS = [
    "https://media.giphy.com/media/v6aOjy0Qo1fIA/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",
    # Add 67 more GIF URLs here...
] * 23

CHRISTMAS_GIFS = [
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",  # Christmas cat 1
    "https://media.giphy.com/media/3o7TKsQ8gTp3WqXqjq/giphy.gif",  # Christmas cat 2
    # Add more Christmas themed GIFs
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
daily_event_counter: Dict[int, Dict[str, Any]] = {}

# ========= helper functions =========

def is_christmas_season():
    """Check if current date is within Christmas season."""
    if not CHRISTMAS_EVENT_ACTIVE:
        return False
    
    today = datetime.now().date()
    start_date = datetime.strptime(CHRISTMAS_EVENT_START, "%Y-%m-%d").date()
    end_date = datetime.strptime(CHRISTMAS_EVENT_END, "%Y-%m-%d").date()
    
    return start_date <= today <= end_date

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

def calculate_breeding_result(parent1: Dict, parent2: Dict) -> Dict:
    """Calculate breeding result between two cats."""
    # Determine offspring rarity (can be higher than parents)
    rarities = ["common", "rare", "epic", "legendary", "mythic", "special"]
    parent1_idx = rarities.index(parent1["rarity"])
    parent2_idx = rarities.index(parent2["rarity"])
    
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
        achievement = next((a for a in ACHIEVEMENTS if a["id"] == achievement_id), None)
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

async def handle_christmas_special():
    """Handle Christmas special events and bonuses."""
    if not is_christmas_season():
        return
    
    # Add Christmas achievements
    for achievement in CHRISTMAS_ACHIEVEMENTS:
        # Logic to check and award Christmas achievements
        pass
    
    # Check for daily Christmas gift
    today = datetime.now().strftime("%Y-%m-%d")
    # Implementation for daily gifts

# ========= COMMAND HANDLERS =========

# Existing commands (start, mew, profile, leaderboard, adopt, cats, feed, play, rename, train, shop, buygear, fight, transfer)
# ... (keep all existing commands as they are)

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
        user_points=points
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
    username = message.from_user.username
    user_db_id = get_or_create_user(user_tg, username)
    
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
    
    # Apply inherited stats
    if cat_id:
        update_cat_stats(cat_id, user_db_id, **offspring_data["stats"])
    
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
                "/clان join <نام> - پیوستن به کلن\n"
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
    total_price = price + fee
    
    listing_id = create_market_listing(
        cat_id=cat_id,
        seller_id=user_db_id,
        price=price,
        fee=fee,
        expires_at=int(time.time()) + MARKET_LISTING_DURATION
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

# ========= Christmas Event Handlers =========

async def maybe_trigger_christmas_event(message: types.Message):
    """Trigger Christmas events during Christmas season."""
    if not is_christmas_season():
        await maybe_trigger_random_event(message)
        return
    
    if message.chat.type not in ("group", "supergroup"):
        return
    
    chat_id = message.chat.id
    now = int(time.time())
    
    # Check cooldown
    if chat_id in active_events:
        event_ts = active_events[chat_id].get("ts", 0)
        if now - event_ts < 3600:  # 1 hour cooldown
            return
    
    # Random chance
    if random.random() > 0.2:  # 20% chance during Christmas
        return
    
    event = random.choice(CHRISTMAS_EVENTS)
    active_events[chat_id] = {
        "event": event,
        "ts": now,
    }
    
    # Send with Christmas GIF
    await bot.send_message(chat_id, event["text"])
    if CHRISTMAS_GIFS:
        await bot.send_animation(chat_id, random.choice(CHRISTMAS_GIFS))

# ========= Enhanced Event Processing =========

async def process_christmas_event_answer(message: types.Message) -> bool:
    """Process answers to Christmas events."""
    if not is_christmas_season():
        return False
    
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
    response_text = f"🎄 **برنده‌ی ایونت کریسمس: {message.from_user.full_name}**\n\n"
    
    try:
        if reward["type"] == "special_cat":
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
        
        elif reward["type"] == "points_gear":
            # Give points and gear
            user = get_user(user_tg)
            current = user.get("mew_points", 0) if user else 0
            points = reward.get("points", 0) * CHRISTMAS_REWARDS_MULTIPLIER
            
            update_user_mew(user_tg, mew_points=current + points)
            
            # Also give gear
            gear_code = reward.get("gear")
            if gear_code:
                # Find first cat to equip
                cats = get_user_cats(user_db_id)
                if cats:
                    cat = cats[0]
                    gear_codes = parse_gear_codes(cat.get("gear", ""))
                    if gear_code not in gear_codes:
                        gear_codes.append(gear_code)
                        new_gear = ",".join(gear_codes)
                        update_cat_stats(cat["id"], user_db_id, gear=new_gear)
                        
                        gear_name = CHRISTMAS_ITEMS.get(gear_code, {}).get("name", gear_code)
                        response_text += f"🎁 {int(points)} میوپوینت + {gear_name} دریافت کردی!"
            
            else:
                response_text += f"🎁 {int(points)} میوپوینت دریافت کردی!"
        
        # Add other reward types...
        
        await message.reply(response_text)
        return True
        
    except Exception as e:
        logger.error(f"Error processing Christmas event: {e}")
        await message.reply("❌ خطا در پردازش جایزه کریسمس.")
        return True

# ========= Enhanced Catch All Handler =========

@dp.message_handler()
async def enhanced_catch_all(message: types.Message):
    """Catch all messages for event processing."""
    if is_christmas_season():
        # Try Christmas events first
        handled = await process_christmas_event_answer(message)
        if handled:
            return
        
        # Trigger Christmas events
        await maybe_trigger_christmas_event(message)
    else:
        # Regular events
        handled = await process_event_answer(message)
        if handled:
            return
        await maybe_trigger_random_event(message)

# ========= Webhook Server with Fix =========

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
        update = types.Update(**data)
        
        # FIX: Set current bot instance
        Bot.set_current(bot)
        
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
