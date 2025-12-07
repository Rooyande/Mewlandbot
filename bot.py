import logging
import os
import random
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.utils.exceptions import TelegramAPIError
from aiogram.contrib.fsm_storage.memory import MemoryStorage

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

# Use MemoryStorage for state
storage = MemoryStorage()
bot = Bot(BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=storage)

# ========= GAME CONFIG =========

MEW_COOLDOWN = 7 * 60       # 7 minutes
PASSIVE_MIN_INTERVAL = 15 * 60  # only recalc passive income every 15 minutes

# hunger / happiness decay
HUNGER_DECAY_PER_HOUR = 8   # Increased decay rate
HAPPINESS_DECAY_PER_HOUR = 5

# Cat death thresholds
MIN_HUNGER_FOR_DEATH = 0
MIN_HAPPINESS_FOR_DEATH = 0

# rarity config: price & base meow/hour
RARITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "common":    {"price": 200,   "base_mph": 1.0, "emoji": "⚪️"},
    "rare":      {"price": 800,   "base_mph": 3.0, "emoji": "🟦"},
    "epic":      {"price": 2500,  "base_mph": 7.0, "emoji": "🟪"},
    "legendary": {"price": 7000,  "base_mph": 15.0, "emoji": "🟨"},
    "mythic":    {"price": 15000, "base_mph": 30.0, "emoji": "🟥"},
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

# XP system
BASE_XP_PER_LEVEL = 100
XP_MULTIPLIER = 1.5  # Each level requires more XP

# gear shop: item_code -> stats
GEAR_ITEMS: Dict[str, Dict[str, Any]] = {
    "scarf": {
        "name": "🧣 شال گرم",
        "price": 500,
        "mph_bonus": 2.0,
        "power_bonus": 1,
        "agility_bonus": 0,
        "luck_bonus": 0,
        "min_level": 1,
    },
    "bell": {
        "name": "🔔 گردنبند زنگوله‌ای",
        "price": 800,
        "mph_bonus": 3.0,
        "power_bonus": 0,
        "agility_bonus": 1,
        "luck_bonus": 1,
        "min_level": 3,
    },
    "boots": {
        "name": "🥾 چکمه تریپ‌دار",
        "price": 1200,
        "mph_bonus": 1.0,
        "power_bonus": 0,
        "agility_bonus": 3,
        "luck_bonus": 0,
        "min_level": 5,
    },
    "crown": {
        "name": "👑 تاج سلطنتی",
        "price": 3000,
        "mph_bonus": 5.0,
        "power_bonus": 2,
        "agility_bonus": 1,
        "luck_bonus": 2,
        "min_level": 10,
    },
}

# random events
RANDOM_EVENTS = [
    {
        "id": "homeless_cat",
        "text": "📢 رویداد روزانه:\nیک گربه‌ی بی‌خانمان دم گروه پرسه می‌زنه!\nاولین کسی که فقط با ایموجی 🏠 جواب بده، یک گربه‌ی Common می‌بره.",
        "answer": "🏠",
        "reward": {"type": "cat", "rarity": "common"},
    },
    # ... keep other events as they were
]

# in-memory state (for production, move to Redis or database)
active_events: Dict[int, Dict[str, Any]] = {}
daily_event_counter: Dict[str, Dict[str, Any]] = {}  # chat_id:date -> count

# ========= helper functions =========

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
    if hunger <= MIN_HUNGER_FOR_DEATH or happiness <= MIN_HAPPINESS_FOR_DEATH:
        return None  # Cat died
    
    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["last_tick_ts"] = now
    
    return cat

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
    key = f"{chat_id}:{today}"
    
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
    
    event = random.choice(RANDOM_EVENTS)
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
        await message.reply("خطا در ایجاد کاربر. لطفا دوباره امتحان کنید.")
        return True
    
    reward = event["reward"]
    response_text = f"🎉 برنده‌ی رویداد: {message.from_user.full_name}\n"
    
    try:
        if reward["type"] == "points":
            user = get_user(user_tg)
            current = user.get("mew_points", 0) if user else 0
            amount = reward["amount"]
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
                response_text += "❌ خطا در ایجاد گربه. لطفا دوباره امتحان کنید."
        
        elif reward["type"] == "cat_random_common_rare":
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
        
        elif reward["type"] == "points_plus_happy":
            user = get_user(user_tg)
            current = user.get("mew_points", 0) if user else 0
            points = reward.get("points", 0)
            happy = reward.get("happy", 0)
            
            update_user_mew(user_tg, mew_points=current + points)
            
            cats = get_user_cats(user_db_id)
            if cats:
                cat = random.choice(cats)
                cat = apply_cat_tick(cat)
                if cat:  # Cat is still alive
                    new_happy = min(100, cat.get("happiness", 0) + happy)
                    update_cat_stats(
                        cat_id=cat["id"],
                        owner_id=user_db_id,
                        happiness=new_happy,
                        last_tick_ts=cat.get("last_tick_ts", int(time.time()))
                    )
                    response_text += f"🎁 {points} میوپوینت + {happy} خوشحالی برای {cat['name']} دریافت کردی!"
                else:
                    response_text += f"🎁 {points} میوپوینت دریافت کردی (گربه‌ات مرده است!)"
            else:
                response_text += f"🎁 {points} میوپوینت دریافت کردی (هنوز گربه‌ای نداری)"
        
        elif reward["type"] == "happy_only":
            cats = get_user_cats(user_db_id)
            if cats:
                cat = random.choice(cats)
                cat = apply_cat_tick(cat)
                if cat:
                    happy = reward.get("happy", 0)
                    new_happy = min(100, cat.get("happiness", 0) + happy)
                    update_cat_stats(
                        cat_id=cat["id"],
                        owner_id=user_db_id,
                        happiness=new_happy,
                        last_tick_ts=cat.get("last_tick_ts", int(time.time()))
                    )
                    response_text += f"😺 {happy} خوشحالی برای {cat['name']} دریافت کردی!"
                else:
                    response_text += "😿 گربه‌ات مرده است!"
            else:
                response_text += "😿 هنوز گربه‌ای نداری."
        
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
        await message.reply("❌ خطا در پردازش جایزه. لطفا دوباره امتحان کنید.")
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
        await message.reply("❌ خطا در ایجاد حساب کاربری. لطفا دوباره امتحان کنید.")
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
            "برای دیدن همه دستورات: /help"
        )
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
            "💰 **انواع گربه:**\n"
            "common(200), rare(800), epic(2500), legendary(7000), mythic(15000)"
        )
    
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
    
    if passive_gained > 0:
        text += f"\n💤 در این بازدید {passive_gained} امتیاز غیرفعال گرفتی!"
    
    await message.reply(text, parse_mode=types.ParseMode.MARKDOWN)

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
    if points < price:
        await message.reply(
            f"❌ امتیاز کافی نیست!\n"
            f"💰 نیاز: {price} | 💎 دارایی: {points}\n"
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
    
    # Send success message
    text = f"🎉 **گربه جدید گرفتی!**\n\n"
    text += f"{rarity_emoji(rarity)} **{name}**\n"
    text += f"🎯 عنصر: {element}\n"
    text += f"✨ خوی: {trait}\n"
    text += f"💰 قیمت: {price} امتیاز\n"
    text += f"📊 ID: {cat_id}\n\n"
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
            f"   ⚔️ قدرت: {stats['power']} | 🌀 چابکی: {stats['agility']} | 🍀 شانس: {stats['luck']}\n"
            f"   💰 درآمد: {mph:.1f} میو/ساعت\n"
        )
        
        if gear_text:
            cat_info += f"   🛡️ تجهیزات: {gear_text}\n"
        
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
        await message.reply("❌ حداکثر مقدار 100 است!")
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

# ... Continue with other commands (rename, train, shop, buygear, fight, transfer)
# They should follow the same pattern with proper error handling and updates

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

# ========= catch-all for emoji events =========

@dp.message_handler()
async def catch_all(message: types.Message):
    """Catch all messages for event processing."""
    handled = await process_event_answer(message)
    if not handled:
        # You can add other message processing here
        pass

# ========= webhook server =========

async def handle_root(request: web.Request):
    return web.Response(text="Mewland Bot is running! 🐱")

async def handle_webhook(request: web.Request):
    token = request.match_info.get("token")
    if token != BOT_TOKEN:
        return web.Response(status=403, text="Forbidden")
    
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        logger.exception(f"Error processing update: {e}")
        await notify_admin_error(f"Webhook error: {str(e)}")
    
    return web.Response(text="OK")

async def on_startup(app: web.Application):
    """Startup tasks."""
    logger.info("Starting up Mewland Bot...")
    
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
    
    # Notify admin
    try:
        await bot.send_message(ADMIN_ID, "🤖 Mewland Bot started successfully!")
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
