# bot.py
import os
import time
import random
import logging

from aiohttp import web

from aiogram import Bot, Dispatcher, types
from aiogram.utils.exceptions import TelegramAPIError
from aiogram.contrib.middlewares.logging import LoggingMiddleware

# ---- import توابع دیتابیس از db.py ----
from db import (
    get_or_create_user,
    get_user,
    update_user_mew,
    get_user_cats,
    add_cat,
    get_cat,
    update_cat_stats,
    rename_cat,
    set_cat_owner,
    get_leaderboard,
    register_user_group,
)

# ---------- تنظیمات پایه ----------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

# آی‌دی ادمین برای گرفتن ارورها
ADMIN_ID = int(os.getenv("ADMIN_ID", "8423995337"))

# کوول‌داون و پاداش میو
MEW_COOLDOWN = 7 * 60  # 7 دقیقه
MEW_REWARD = 10        # امتیاز برای هر میو موفق

# decay گربه
HUNGER_DECAY_PER_HOUR = 4      # هر ساعت ۴ تا گرسنگی کم بشه
HAPPINESS_DECAY_PER_HOUR = 2   # هر ساعت ۲ تا شادی کم بشه
DEATH_GRACE_HOURS = 36         # بعد از ۳۶ ساعت بدون رسیدگی تو گرسنگی صفر = مرگ

# قیمت گربه‌ها براساس rarity
CAT_COST = {
    "common": 100,
    "rare": 250,
    "epic": 800,
    "legendary": 2000,
    "mythic": 4000,
}

RARITY_WEIGHTS = [
    ("common", 60),
    ("rare", 25),
    ("epic", 10),
    ("legendary", 4),
    ("mythic", 1),
]

ELEMENTS = ["fire", "water", "earth", "air", "shadow", "light"]
TRAITS = ["lazy", "hyper", "greedy", "loyal", "chaotic", "smart"]

PLAY_GIFS = [
    # اینجا می‌تونی لینک گیف‌هات رو بذاری
    # "https://media.tenor.com/.....gif",
    # "https://i.gifer.com/....gif",
]

bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())


# ---------- helper ها ----------

def choose_rarity(explicit: str | None = None) -> str:
    if explicit:
        r = explicit.lower()
        if r in CAT_COST:
            return r
    total = sum(w for _, w in RARITY_WEIGHTS)
    x = random.randint(1, total)
    cur = 0
    for r, w in RARITY_WEIGHTS:
        cur += w
        if x <= cur:
            return r
    return "common"


def random_cat_stats(rarity: str):
    element = random.choice(ELEMENTS)
    trait = random.choice(TRAITS)
    name = {
        "common": ["مومو", "پوپو", "کیتی", "میسی"],
        "rare": ["شدو", "فِلِیم", "اسپارک"],
        "epic": ["نُووا", "گَلِکسی", "فِینیکس"],
        "legendary": ["اژدرکَت", "شیدوکلاو"],
        "mythic": ["کاسْمیک", "خدای میو"],
    }.get(rarity, ["میو"])
    name = random.choice(name)
    desc = f"یک گربه {rarity} با المان {element} و خصوصیت {trait}."
    return name, element, trait, desc


def format_cat_line(cat: dict) -> str:
    hunger = cat.get("hunger", 0)
    happiness = cat.get("happiness", 0)
    level = cat.get("level", 1)
    xp = cat.get("xp", 0)
    rarity = cat.get("rarity", "unknown")
    name = cat.get("name", "بدون‌نام")
    cid = cat.get("id")

    # تشخیص مرگ بر اساس وضعیت فعلی
    now = int(time.time())
    last_ts = cat.get("last_tick_ts") or cat.get("created_at") or now
    dead = hunger <= 0 and (now - last_ts) >= DEATH_GRACE_HOURS * 3600

    status = "💀 مرده" if dead else "😺 زنده"
    return (
        f"ID: <code>{cid}</code>\n"
        f"اسم: <b>{name}</b>\n"
        f"رتبه: {rarity}\n"
        f"لول: {level} (XP: {xp})\n"
        f"گشنگی: {hunger}/100\n"
        f"خوشحالی: {happiness}/100\n"
        f"وضعیت: {status}\n"
        f"------------------------"
    )


def apply_cat_decay(cat: dict) -> dict:
    """
    سایه‌وار زمان رو روی گربه‌ها اعمال می‌کنیم:
    - کاهش گرسنگی و شادی بر اساس last_tick_ts
    - اگر ۳۶ ساعت در حالت گرسنگی صفر بوده => مرگ
    فقط وقتی از این گربه در بازی استفاده می‌کنیم صدا زده میشه.
    """
    now = int(time.time())
    last_ts = cat.get("last_tick_ts") or cat.get("created_at") or now
    elapsed = max(0, now - last_ts)

    hunger = int(cat.get("hunger", 60))
    happiness = int(cat.get("happiness", 60))
    xp = int(cat.get("xp", 0))
    level = int(cat.get("level", 1))

    changed = False

    if elapsed > 0:
        hours = elapsed / 3600.0

        # اگر قبلاً هم صفر نبوده، کم کنیم
        if hunger > 0:
            new_hunger = max(0, hunger - int(hours * HUNGER_DECAY_PER_HOUR))
            if new_hunger != hunger:
                hunger = new_hunger
                changed = True

        if happiness > 0:
            new_happy = max(0, happiness - int(hours * HAPPINESS_DECAY_PER_HOUR))
            if new_happy != happiness:
                happiness = new_happy
                changed = True

    # بررسی مرگ
    dead = False
    if hunger <= 0 and (now - last_ts) >= DEATH_GRACE_HOURS * 3600:
        dead = True
        hunger = 0
        happiness = 0
        changed = True

    if changed:
        # last_tick_ts رو آپدیت می‌کنیم فقط اگر هنوز زنده است
        ts_to_store = last_ts if dead else now
        update_cat_stats(
            cat_id=cat["id"],
            owner_id=cat["owner_id"],
            hunger=hunger,
            happiness=happiness,
            xp=xp,
            level=level,
            last_tick_ts=ts_to_store,
        )
        cat["hunger"] = hunger
        cat["happiness"] = happiness
        cat["xp"] = xp
        cat["level"] = level
        cat["last_tick_ts"] = ts_to_store

    cat["dead"] = dead
    return cat


def can_overfeed_kill(cat: dict, added_amount: int) -> tuple[bool, str]:
    """
    رفتار overfeed:
    - اگر گرسنگی بالای ۹۵ و داری زیاد غذا می‌دی، گربه مقاومت می‌کنه و خوشحالی میاد پایین
    - اگر همچنان وضعیت بد باشه و هی غذا بدی => احتمال مرگ
    برای سادگی، بدون ستون اضافه تو دیتابیس، با ترکیب hunger + happiness قضاوت می‌کنیم.
    """
    hunger = cat.get("hunger", 0)
    happiness = cat.get("happiness", 0)

    if hunger < 95:
        return False, ""

    # مرحله اول: تذکر
    if happiness > 40:
        return False, "گربه‌ات داره می‌ترکه 😾 کمی بهش استراحت بده، انقد غذا نده."

    # مرحله دوم: مریض شدن
    if happiness > 20:
        return False, "گربه‌ات یه کم بدحال شد 🤢 زیاد بهش خوراکی دادی، شادی‌ش کم شد."

    # مرحله سوم: مرگ
    return True, "زیادی بهش غذا دادی و حالش خیلی بد شد... 😔 گربه‌ات از دست رفت."


async def safe_reply(message: types.Message, text: str):
    try:
        await message.reply(text)
    except TelegramAPIError as e:
        logger.error("Failed to send reply: %r", e)


# ---------- هندل ارورها ----------

@dp.errors_handler()
async def global_error_handler(update, exception):
    logger.exception("Unhandled error: %r", exception)
    try:
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ خطا در بات:\n<code>{repr(exception)}</code>",
        )
    except TelegramAPIError:
        pass
    return True


# ---------- دستورات /start و /help ----------

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = get_or_create_user(message.from_user.id, message.from_user.username)
    if message.chat.type in ("group", "supergroup"):
        register_user_group(user_id, message.chat.id)

    txt = (
        "سلام به میولند! 😺\n\n"
        "هر ۷ دقیقه یه بار می‌تونی «/mew» بزنی و میوپوینت بگیری.\n"
        "با میوپوینت می‌تونی گربه با rarity مختلف بگیری و بزرگشون کنی.\n\n"
        "برای دیدن دستورات: /help"
    )
    await safe_reply(message, txt)


@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    txt = (
        "📜 لیست دستورات اصلی میولند:\n\n"
        "امتیاز:\n"
        "  /mew – هر ۷ دقیقه یک بار، ۱۰ میوپوینت می‌گیری.\n"
        "  /mystats یا /profile – وضعیت کلی تو (پوینت، تعداد گربه‌ها...).\n"
        "  /leaderboard – جدول برترین‌ها بر اساس mew_points.\n\n"
        "گربه‌ها:\n"
        "  /mycats – لیست گربه‌های تو.\n"
        "  /newcat rarity – گرفتن گربه جدید (common / rare / epic / legendary / mythic).\n"
        "  /feed cat_id amount – غذا دادن به گربه.\n"
        "  /play cat_id – بازی کردن با گربه.\n"
        "  /rename cat_id اسم_جدید – عوض کردن اسم گربه.\n"
        "  /transfer cat_id @username – انتقال گربه به یک نفر دیگر.\n\n"
        "نکته: اگر گربه‌ات رو ول کنی و ۳۶ ساعت در گرسنگی صفر بمونه، می‌میره 💀"
    )
    await safe_reply(message, txt)


# ---------- امتیازدهی /mew ----------

@dp.message_handler(commands=["mew"])
async def cmd_mew(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username

    user_id = get_or_create_user(tg_id, username)
    if message.chat.type in ("group", "supergroup"):
        register_user_group(user_id, message.chat.id)

    user = get_user(tg_id)
    now = int(time.time())
    last = user.get("last_mew_ts")

    if last is not None:
        delta = now - int(last)
        if delta < MEW_COOLDOWN:
            remain = MEW_COOLDOWN - delta
            mins = remain // 60
            secs = remain % 60
            await safe_reply(
                message,
                f"هنوز باید {mins} دقیقه و {secs} ثانیه صبر کنی تا دوباره /mew بزنی 😼",
            )
            return

    new_points = int(user.get("mew_points", 0)) + MEW_REWARD
    update_user_mew(tg_id, mew_points=new_points, last_mew_ts=now)

    await safe_reply(
        message,
        f"میووو! 😺\n"
        f"+{MEW_REWARD} میوپوینت گرفتی.\n"
        f"مجموع میوپوینت‌هات الان: <b>{new_points}</b>",
    )


# ---------- پروفایل /mystats /profile ----------

@dp.message_handler(commands=["mystats", "profile"])
async def cmd_mystats(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username

    user_id = get_or_create_user(tg_id, username)
    if message.chat.type in ("group", "supergroup"):
        register_user_group(user_id, message.chat.id)

    user = get_user(tg_id)
    cats = get_user_cats(user_id)

    points = int(user.get("mew_points", 0))
    total_cats = len(cats)

    txt = (
        f"👤 پروفایل تو:\n\n"
        f"یوزرنیم: @{username if username else 'بدون یوزرنیم'}\n"
        f"مجموع میوپوینت: <b>{points}</b>\n"
        f"تعداد گربه‌ها: <b>{total_cats}</b>\n"
    )
    await safe_reply(message, txt)


# ---------- لیست گربه‌ها /mycats ----------

@dp.message_handler(commands=["mycats"])
async def cmd_mycats(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username

    user_id = get_or_create_user(tg_id, username)
    cats = get_user_cats(user_id)

    if not cats:
        await safe_reply(
            message,
            "هنوز هیچ گربه‌ای نداری 😿\nبا دستور زیر شروع کن:\n/newcat common",
        )
        return

    # decay را روی هر گربه اعمال می‌کنیم
    refreshed = []
    for c in cats:
        refreshed.append(apply_cat_decay(c))

    lines = [format_cat_line(c) for c in refreshed]
    txt = "🐾 گربه‌های تو:\n\n" + "\n".join(lines)
    await safe_reply(message, txt)


# ---------- گرفتن گربه جدید /newcat ----------

@dp.message_handler(commands=["newcat"])
async def cmd_newcat(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username

    args = message.get_args().split()
    rarity_arg = args[0].lower() if args else None
    rarity = choose_rarity(rarity_arg)

    if rarity_arg and rarity_arg not in CAT_COST:
        await safe_reply(
            message,
            "rarity نامعتبره. یکی از اینا رو بزن:\n"
            "common, rare, epic, legendary, mythic",
        )
        return

    user_id = get_or_create_user(tg_id, username)
    user = get_user(tg_id)
    points = int(user.get("mew_points", 0))
    cost = CAT_COST[rarity]

    if points < cost:
        await safe_reply(
            message,
            f"برای گربه {rarity} حداقل {cost} میوپوینت لازم داری.\n"
            f"الان فقط {points} داری 😿"
        )
        return

    # کم کردن امتیاز
    update_user_mew(tg_id, mew_points=points - cost)

    # ساختن گربه
    name, element, trait, desc = random_cat_stats(rarity)
    cat_id = add_cat(
        owner_id=user_id,
        name=name,
        rarity=rarity,
        element=element,
        trait=trait,
        description=desc,
    )

    await safe_reply(
        message,
        f"🎉 تبریک! یک گربه جدید گرفتی:\n\n"
        f"ID: <code>{cat_id}</code>\n"
        f"اسم: <b>{name}</b>\n"
        f"رتبه: {rarity}\n"
        f"المان: {element}\n"
        f"خصوصیت: {trait}\n"
        f"قیمت: {cost} میوپوینت (از حساب کم شد)\n\n"
        f"گربه‌هات رو با /mycats ببین."
    )


# ---------- غذا دادن /feed ----------

@dp.message_handler(commands=["feed"])
async def cmd_feed(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username

    user_id = get_or_create_user(tg_id, username)

    args = message.get_args().split()
    if len(args) != 2:
        await safe_reply(message, "استفاده: /feed cat_id amount")
        return

    try:
        cat_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await safe_reply(message, "cat_id و amount باید عدد باشن.")
        return

    if amount <= 0:
        await safe_reply(message, "مقدار غذا باید مثبت باشه.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await safe_reply(message, "چنین گربه‌ای برای تو پیدا نشد.")
        return

    cat = apply_cat_decay(cat)
    if cat.get("dead"):
        await safe_reply(
            message,
            "این گربه متأسفانه مرده 💀\nنمی‌تونی بهش غذا بدی.",
        )
        return

    hunger_before = int(cat.get("hunger", 0))
    happiness = int(cat.get("happiness", 0))
    xp = int(cat.get("xp", 0))
    level = int(cat.get("level", 1))

    # چک overfeed
    may_die, overfeed_msg = can_overfeed_kill(cat, amount)
    if may_die:
        # مرگ بر اثر پرخوری
        update_cat_stats(
            cat_id=cat_id,
            owner_id=user_id,
            hunger=0,
            happiness=0,
            xp=xp,
            level=level,
            last_tick_ts=int(time.time()),
        )
        await safe_reply(message, overfeed_msg)
        return

    # خوردن نرمال
    new_hunger = min(100, hunger_before + amount)

    # کمی شادی و xp
    happiness = min(100, happiness + amount // 5)
    xp += amount // 10

    # لول آپ ساده
    while xp >= level * 20:
        xp -= level * 20
        level += 1

    update_cat_stats(
        cat_id=cat_id,
        owner_id=user_id,
        hunger=new_hunger,
        happiness=happiness,
        xp=xp,
        level=level,
        last_tick_ts=int(time.time()),
    )

    txt = (
        f"🍲 به گربه‌ات غذا دادی!\n"
        f"ID: <code>{cat_id}</code>\n"
        f"گشنگی: {hunger_before} ➜ {new_hunger}\n"
        f"خوشحالی: {cat.get('happiness', 0)} ➜ {happiness}\n"
        f"لول: {cat.get('level', 1)} (XP: {xp})\n"
    )
    if overfeed_msg:
        txt += "\n" + overfeed_msg

    await safe_reply(message, txt)


# ---------- بازی کردن /play ----------

@dp.message_handler(commands=["play"])
async def cmd_play(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    args = message.get_args().split()
    if len(args) != 1:
        await safe_reply(message, "استفاده: /play cat_id")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await safe_reply(message, "cat_id باید عدد باشه.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await safe_reply(message, "چنین گربه‌ای برای تو پیدا نشد.")
        return

    cat = apply_cat_decay(cat)
    if cat.get("dead"):
        await safe_reply(
            message,
            "این گربه مرده 💀 و نمی‌تونه بازی کنه.",
        )
        return

    hunger = int(cat.get("hunger", 0))
    happiness = int(cat.get("happiness", 0))
    xp = int(cat.get("xp", 0))
    level = int(cat.get("level", 1))

    # اگر خیلی گشنه است، کم‌تر اثر بگیره
    if hunger < 20:
        delta_happy = 5
    else:
        delta_happy = 15

    new_happy = min(100, happiness + delta_happy)
    xp += 5

    while xp >= level * 20:
        xp -= level * 20
        level += 1

    update_cat_stats(
        cat_id=cat_id,
        owner_id=user_id,
        hunger=hunger,  # اینجا گشنگی عوض نمی‌کنیم
        happiness=new_happy,
        xp=xp,
        level=level,
        last_tick_ts=int(time.time()),
    )

    # اگر گیف تعریف کرده باشی
    if PLAY_GIFS:
        gif_url = random.choice(PLAY_GIFS)
        try:
            await bot.send_animation(
                chat_id=message.chat.id,
                animation=gif_url,
                caption=(
                    f"🎮 گربه‌ات بازی کرد!\n"
                    f"ID: <code>{cat_id}</code>\n"
                    f"خوشحالی: {happiness} ➜ {new_happy}\n"
                    f"لول: {level} (XP: {xp})"
                ),
                reply_to_message_id=message.message_id,
            )
            return
        except TelegramAPIError:
            pass

    # اگر گیف نداشتیم یا ارور داد
    await safe_reply(
        message,
        f"🎮 گربه‌ات بازی کرد!\n"
        f"ID: <code>{cat_id}</code>\n"
        f"خوشحالی: {happiness} ➜ {new_happy}\n"
        f"لول: {level} (XP: {xp})"
    )


# ---------- عوض کردن اسم /rename ----------

@dp.message_handler(commands=["rename"])
async def cmd_rename(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    args = message.get_args().split()
    if len(args) < 2:
        await safe_reply(message, "استفاده: /rename cat_id اسم_جدید")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await safe_reply(message, "cat_id باید عدد باشه.")
        return

    new_name = " ".join(args[1:]).strip()
    if not new_name:
        await safe_reply(message, "اسم جدید نباید خالی باشه.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await safe_reply(message, "چنین گربه‌ای برای تو پیدا نشد.")
        return

    rename_cat(user_id, cat_id, new_name)
    await safe_reply(
        message,
        f"✅ اسم گربه با ID <code>{cat_id}</code> شد: <b>{new_name}</b>",
    )


# ---------- انتقال گربه /transfer ----------

@dp.message_handler(commands=["transfer"])
async def cmd_transfer(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    args = message.get_args().split()
    if len(args) != 2:
        await safe_reply(message, "استفاده: /transfer cat_id @username")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await safe_reply(message, "cat_id باید عدد باشه.")
        return

    target_username = args[1]
    if not target_username.startswith("@"):
        await safe_reply(message, "یوزرنیم باید با @ شروع بشه.")
        return

    # پیدا کردن یوزر هدف از بین یوزرهایی که تا حالا با بات کار کردن:
    # اینجا ساده‌سازیش می‌کنیم: فقط اگر قبلاً /start زده باشه (get_user رویش جواب بده)
    # Supabase ما فقط با telegram_id کار می‌کند، نه username، پس انتقال را
    # به طور کامل و دقیق بر اساس username نمی‌توانیم انجام دهیم بدون جدول اضافه.
    await safe_reply(
        message,
        "فعلاً انتقال بر اساس @username به‌صورت کامل پیاده‌سازی نشده چون در دیتابیس فقط telegram_id ذخیره می‌کنیم.\n"
        "می‌تونیم بعداً یه جدول map بین username و telegram_id اضافه کنیم تا این فیچر کامل بشه."
    )


# ---------- لیدربرد /leaderboard ----------

@dp.message_handler(commands=["leaderboard"])
async def cmd_leaderboard(message: types.Message):
    try:
        rows = get_leaderboard(limit=10)
    except Exception as e:
        logger.exception("Error fetching leaderboard: %r", e)
        await safe_reply(message, "خطا در گرفتن لیدربرد، بعداً امتحان کن.")
        return

    if not rows:
        await safe_reply(message, "فعلاً کسی تو لیدربرد نیست 😹")
        return

    lines = []
    for i, row in enumerate(rows, start=1):
        uname = row.get("username") or ("user_" + str(row.get("telegram_id")))
        pts = row.get("mew_points", 0)
        lines.append(f"{i}. @{uname} – <b>{pts}</b> میوپوینت")

    txt = "🏆 لیدربرد میولند:\n\n" + "\n".join(lines)
    await safe_reply(message, txt)


# ---------- تریگر ساده برای کلمه mew بدون / ----------

@dp.message_handler(regexp=r"^mew$", content_types=types.ContentTypes.TEXT)
async def handle_plain_mew(message: types.Message):
    # راحت می‌تونیم ریدایرکت کنیم به /mew
    message.text = "/mew"
    await cmd_mew(message)


# ---------- aiohttp و وبهوک ----------

async def handle_root(request):
    return web.Response(text="Mewland bot is running.")


async def handle_webhook(request):
    token = request.match_info.get("token")
    if token != BOT_TOKEN:
        return web.Response(status=403)

    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return web.json_response({"ok": True})


async def on_startup(app: web.Application):
    # ست کردن وبهوک
    base_url = os.getenv("RENDER_EXTERNAL_URL")
    if not base_url:
        logger.warning("RENDER_EXTERNAL_URL تنظیم نشده، وبهوک ست نمی‌شود.")
        return
    webhook_url = base_url.rstrip("/") + f"/webhook/{BOT_TOKEN}"
    await bot.set_webhook(webhook_url)
    logger.info("Webhook set to %s", webhook_url)


async def on_cleanup(app: web.Application):
    try:
        await bot.delete_webhook()
        logger.info("Webhook deleted.")
    except TelegramAPIError as e:
        logger.error("Failed to delete webhook: %r", e)


def main():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_post("/webhook/{token}", handle_webhook)

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
