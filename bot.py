# bot.py
import asyncio
import logging
import os
import random
import time

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import CommandStart, CommandHelp
from aiogram.utils.markdown import quote_html
from aiogram.utils.exceptions import TelegramAPIError
from aiogram import Dispatcher, Bot

from db import (
    init_db,
    get_or_create_user,
    update_user_mew,
    get_user_cats,
    add_cat,
    get_cat,
    update_cat_fields,
    rename_cat,
    set_cat_owner,
    update_cat_appearance,
    get_leaderboard,
    register_user_group,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN ست نشده است.")

ADMIN_ID = 8423995337  # برای ارسال ارورها به PV

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# Render معمولاً اینو ست می‌کند
APP_URL = os.getenv("RENDER_EXTERNAL_URL")  # مثل https://mewlandbot.onrender.com
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("PORT", "10000"))

# ---------- تنظیمات بازی ----------

MEW_COOLDOWN = 7 * 60  # ۷ دقیقه
CAT_TICK_INTERVAL = 3 * 3600  # هر ۳ ساعت یک تیک برای گرسنگی/شادمانی
HUNGER_DECAY_PER_TICK = 10
HAPPINESS_DECAY_PER_TICK = 5
CAT_DEATH_GRACE = 36 * 3600  # اگر گرسنگی ۰ بود و ۳۶ ساعت بگذره => مرگ

TRANSFER_COST = 50  # هزینه انتقال گربه
EVENTS_PER_DAY = 2  # تعداد ایونت رندوم در روز برای هر گروه

RARITY_COSTS = {
    "common": 100,
    "rare": 100,
    "epic": 500,
    "legendary": 2000,
    "mythic": 2000,
}

RARITIES = [
    ("common", 60),
    ("rare", 25),
    ("epic", 10),
    ("legendary", 4),
    ("mythic", 1),
]

ELEMENTS = ["fire", "water", "earth", "air", "shadow", "light"]
TRAITS = ["sleepy", "chaotic", "grumpy", "playful", "lazy", "curious"]

PLAY_GIFS = [
    # اینجا file_id های گیف‌ها رو خودت بعداً جایگزین کن
    # "CgACAgQAAxkBAAIBZmW...", ...
]

# وضعیت ایونت‌های هر گروه فقط در مموری (بدون سوپابیس)
group_events_state = {}  # chat_id -> dict


# ---------- Helperها ----------

def choose_weighted(options):
    # options: list of (value, weight)
    total = sum(w for _, w in options)
    r = random.uniform(0, total)
    upto = 0
    for value, weight in options:
        if upto + weight >= r:
            return value
        upto += weight
    return options[-1][0]


def make_cat_description(rarity: str, element: str, trait: str) -> str:
    return f"A {rarity} {element} cat, very {trait}."


def compute_cat_state(cat: dict, now: int) -> dict:
    """
    فقط برای نمایش / منطق بازی محلی:
    گرسنگی/شادمانی را بر اساس زمان می‌ریزه پایین
    و اگر گرسنگی ۰ و خیلی گذشته، is_alive را False می‌کند.
    این تابع خودش DB را آپدیت نمی‌کند.
    """
    new_cat = dict(cat)

    last = cat.get("last_tick_ts") or cat.get("created_at") or now
    elapsed = max(0, now - last)
    ticks = elapsed // CAT_TICK_INTERVAL

    hunger = cat.get("hunger", 0)
    happiness = cat.get("happiness", 0)

    if ticks > 0:
        hunger = max(0, hunger - HUNGER_DECAY_PER_TICK * ticks)
        happiness = max(0, happiness - HAPPINESS_DECAY_PER_TICK * ticks)

    is_alive = cat.get("is_alive", True)
    death_ts = cat.get("death_ts")

    if is_alive:
        if hunger <= 0 and elapsed >= CAT_DEATH_GRACE:
            is_alive = False
            death_ts = now

    new_cat["hunger"] = hunger
    new_cat["happiness"] = happiness
    new_cat["is_alive"] = is_alive
    new_cat["death_ts"] = death_ts

    return new_cat


def get_level_and_xp_after_gain(level: int, xp: int, gain: int):
    xp += gain
    while xp >= 100:
        xp -= 100
        level += 1
    return level, xp


def format_cat(cat: dict) -> str:
    base = f"ID: <code>{cat['id']}</code> | {cat['name']} ({cat['rarity']})\n"
    base += f"عنصر: {cat.get('element', '-')}, خصوصیت: {cat.get('trait', '-')}\n"
    base += f"سطح: {cat.get('level', 1)}, XP: {cat.get('xp', 0)}/100\n"
    base += f"گرسنگی: {cat.get('hunger', 0)}/100 | خوشحالی: {cat.get('happiness', 0)}/100\n"

    if cat.get("appearance"):
        base += f"ظاهر: {quote_html(cat['appearance'])}\n"

    if not cat.get("is_alive", True):
        base += "وضعیت: 💀 مرده\n"
    elif cat.get("is_sick"):
        base += "وضعیت: 🤢 مریض\n"
    else:
        base += "وضعیت: 😺 زنده\n"

    return base


def current_day(now: int | None = None) -> int:
    if now is None:
        now = int(time.time())
    return time.gmtime(now).tm_yday


# ---------- رویدادهای رندوم ----------

RANDOM_EVENTS = [
    {
        "id": "homeless_cat",
        "text": "❗ یک گربهٔ بی‌خونه توی کوچه دیده شد! اولین نفری که ایموجی 🏠 بفرسته، نجاتش می‌ده و جایزه می‌گیره!",
        "trigger": "🏠",
        "reward": ("cat_common", None),
    },
    {
        "id": "fish_thief",
        "text": "🐟 یک گربه داره ماهی می‌دزده! اولین کسی که ایموجی 🚫 بفرسته، جلوی دزدی رو می‌گیره و امتیاز می‌گیره!",
        "trigger": "🚫",
        "reward": ("points", 50),
    },
    {
        "id": "rain_shelter",
        "text": "🌧 بارون اومده و گربه‌ها خیس شدن! اولین کسی که ☂️ بفرسته بهشون پناه می‌ده و امتیاز می‌گیره!",
        "trigger": "☂️",
        "reward": ("points", 40),
    },
    {
        "id": "food_drop",
        "text": "🍣 یک بسته غذای گربه افتاده وسط گروه! اولین کسی که 🍣 بفرسته، صاحبش می‌شه!",
        "trigger": "🍣",
        "reward": ("points", 60),
    },
    {
        "id": "lost_kitten",
        "text": "😿 یک بچه‌گربه گم شده! اولین کسی که 🧭 بفرسته، کمکش می‌کند راه خونه رو پیدا کنه!",
        "trigger": "🧭",
        "reward": ("cat_common", None),
    },
    {
        "id": "playground",
        "text": "🎪 گربه‌ها می‌خوان برن شهربازی! اولین کسی که 🎟 بفرسته، همه رو می‌بره تفریح!",
        "trigger": "🎟",
        "reward": ("points", 70),
    },
    {
        "id": "medicine",
        "text": "💊 یک گربه مریض شده. اولین کسی که 💊 بفرسته، براش دارو می‌گیره و امتیاز می‌گیره!",
        "trigger": "💊",
        "reward": ("points", 80),
    },
    {
        "id": "toy_store",
        "text": "🧸 فروشگاه اسباب‌بازی گربه‌ها حراج زده! اولین کسی که 🧸 بفرسته، یک اسباب‌بازی برای گربه‌ش می‌گیره!",
        "trigger": "🧸",
        "reward": ("points", 60),
    },
    {
        "id": "night_guard",
        "text": "🌙 شب شده و گربه‌ها می‌ترسن. اولین کسی که 🔦 بفرسته، نقش نگهبان شب رو می‌گیره!",
        "trigger": "🔦",
        "reward": ("points", 50),
    },
    {
        "id": "stray_party",
        "text": "🎉 چندتا گربه ولگرد مهمون شدن! اولین کسی که 🎁 بفرسته، میزبانی می‌کنه و هدیه می‌گیره!",
        "trigger": "🎁",
        "reward": ("cat_common", None),
    },
]


async def maybe_trigger_event(message: types.Message):
    """
    در هر پیام گروه چک می‌کنیم آیا وقت یک رویداد جدید هست یا نه.
    بدون استفاده از DB، فقط در RAM.
    """
    if message.chat.type not in ("group", "supergroup"):
        return

    now = int(time.time())
    day = current_day(now)
    chat_id = message.chat.id

    st = group_events_state.get(chat_id)
    if st is None or st.get("day") != day:
        st = {
            "day": day,
            "events_today": 0,
            "next_event_ts": now + random.randint(3600, 4 * 3600),  # بین ۱ تا ۴ ساعت
            "active": None,
        }

    # اگر الان یک ایونت فعال است، کاری نکن
    if st["active"] is not None:
        # اگر منقضی شده، پاکش کن
        if now >= st["active"]["expires"]:
            st["active"] = None
        group_events_state[chat_id] = st
        return

    # اگر سقف امروز پر شده
    if st["events_today"] >= EVENTS_PER_DAY:
        group_events_state[chat_id] = st
        return

    # هنوز وقتش نشده
    if now < st["next_event_ts"]:
        group_events_state[chat_id] = st
        return

    # شروع رویداد جدید
    ev = random.choice(RANDOM_EVENTS)
    msg = await message.answer(ev["text"])

    st["active"] = {
        "id": ev["id"],
        "trigger": ev["trigger"],
        "reward": ev["reward"],
        "message_id": msg.message_id,
        "expires": now + 600,  # ۱۰ دقیقه فرصت
    }
    st["events_today"] += 1
    # زمان بعدی رویداد: بین ۶ تا ۱۲ ساعت بعد
    st["next_event_ts"] = now + random.randint(6 * 3600, 12 * 3600)

    group_events_state[chat_id] = st


async def handle_event_reply(message: types.Message):
    """
    اگر ایونت فعال است و کسی ایموجی درست را فرستاد، جایزه را می‌دهیم.
    """
    if message.chat.type not in ("group", "supergroup"):
        return
    if not message.text:
        return

    chat_id = message.chat.id
    st = group_events_state.get(chat_id)
    if not st or not st.get("active"):
        return

    now = int(time.time())
    active = st["active"]

    if now >= active["expires"]:
        st["active"] = None
        group_events_state[chat_id] = st
        return

    trigger = active["trigger"]
    if trigger not in message.text:
        return

    # این نفر اول بود که درست جواب داد
    user = message.from_user
    user_id, user_row = get_or_create_user(user.id, user.username)

    reward_type, reward_value = active["reward"]
    reward_text = ""

    if reward_type == "points":
        old_points = user_row.get("mew_points", 0)
        new_points = old_points + int(reward_value or 0)
        update_user_mew(user.id, mew_points=new_points)
        reward_text = f"{reward_value} میوپوینت 🎉"
    elif reward_type == "cat_common":
        rarity = "common"
        element = random.choice(ELEMENTS)
        trait = random.choice(TRAITS)
        desc = make_cat_description(rarity, element, trait)
        cat_name = "Stray Kitty"
        new_cat_id = add_cat(
            owner_id=user_id,
            name=cat_name,
            rarity=rarity,
            element=element,
            trait=trait,
            description=desc,
        )
        reward_text = f"یک گربه‌ی جدید ({rarity}) با ID: <code>{new_cat_id}</code> 🐱"

    await message.reply(
        f"🎉 {user.full_name} برنده شد!\nجایزه‌ات: {reward_text}"
    )

    # ایونت رو ببند
    st["active"] = None
    group_events_state[chat_id] = st


# ---------- هندلرهای بات ----------

@dp.message_handler(CommandStart())
async def cmd_start(message: types.Message):
    user_id, _ = get_or_create_user(message.from_user.id, message.from_user.username)
    if message.chat.type in ("group", "supergroup"):
        register_user_group(user_id, message.chat.id)

    text = (
        "به میولَند خوش اومدی! 🐱\n\n"
        "با نوشتن <b>mew</b> (هر ۷ دقیقه یک‌بار) میوپوینت می‌گیری.\n"
        "با میوپوینت‌هات می‌تونی گربه بگیری، غذا بدی، بازی کنی و کلی کار دیگه.\n\n"
        "برای دیدن دستورات: /help"
    )
    await message.reply(text)


@dp.message_handler(CommandHelp())
async def cmd_help(message: types.Message):
    text = (
        "دستورات میولند 🐾\n\n"
        "/mystats - وضعیت خودت (میوپوینت و ...)\n"
        "/mycats - لیست گربه‌هات\n"
        "/newcat [rarity] - گرفتن گربه جدید (مثلاً /newcat common)\n"
        "/feed <cat_id> <amount> - غذا دادن به گربه\n"
        "/play <cat_id> - بازی کردن با گربه (XP و خوشحالی)\n"
        "/rename <cat_id> <name> - عوض کردن اسم گربه\n"
        "/style <cat_id> <ظاهر> - توضیح ظاهر گربه\n"
        "/transfer <cat_id> @user - انتقال گربه با هزینه\n"
        "/leaderboard - جدول امتیازها\n\n"
        "فقط توی گروه‌ها: با نوشتن mew امتیاز می‌گیری و ایونت‌های رندوم هم ممکنه اتفاق بیفته."
    )
    await message.reply(text)


@dp.message_handler(commands=["mystats"])
async def cmd_mystats(message: types.Message):
    user_id, user_row = get_or_create_user(message.from_user.id, message.from_user.username)
    mp = user_row.get("mew_points", 0)
    last_mew = user_row.get("last_mew_ts")
    ago = ""
    if last_mew:
        diff = int(time.time()) - int(last_mew)
        mins = diff // 60
        secs = diff % 60
        ago = f" (آخرین میو: {mins} دقیقه و {secs} ثانیه پیش)"

    await message.reply(
        f"😺 امتیاز میو: <b>{mp}</b>\n"
        f"ID داخلی‌ات: <code>{user_id}</code>\n"
        f"{ago}"
    )


@dp.message_handler(commands=["mycats"])
async def cmd_mycats(message: types.Message):
    user_id, _ = get_or_create_user(message.from_user.id, message.from_user.username)
    cats = get_user_cats(user_id)
    if not cats:
        await message.reply("هنوز هیچ گربه‌ای نداری! با /newcat یکی بگیر 😼")
        return

    now = int(time.time())
    lines = []
    for c in cats:
        cc = compute_cat_state(c, now)
        lines.append(format_cat(cc))

    await message.reply("\n\n".join(lines))


@dp.message_handler(commands=["newcat"])
async def cmd_newcat(message: types.Message):
    user_id, user_row = get_or_create_user(message.from_user.id, message.from_user.username)
    args = message.get_args().strip().lower().split() if message.get_args() else []
    if args:
        requested_rarity = args[0]
        if requested_rarity not in RARITY_COSTS:
            await message.reply("rarity نامعتبره. یکی از اینا رو بزن: common, rare, epic, legendary, mythic")
            return
        rarity = requested_rarity
    else:
        rarity = choose_weighted(RARITIES)

    cost = RARITY_COSTS.get(rarity, 100)
    current_points = user_row.get("mew_points", 0)

    if current_points < cost:
        await message.reply(f"برای گرفتن گربه‌ی {rarity} حداقل {cost} میوپوینت لازم داری. امتیازت کمه 😿")
        return

    # ساخت گربه
    element = random.choice(ELEMENTS)
    trait = random.choice(TRAITS)
    desc = make_cat_description(rarity, element, trait)
    name = f"{rarity.capitalize()} Cat"

    cat_id = add_cat(
        owner_id=user_id,
        name=name,
        rarity=rarity,
        element=element,
        trait=trait,
        description=desc,
    )

    # کم کردن امتیاز
    new_points = current_points - cost
    update_user_mew(message.from_user.id, mew_points=new_points)

    await message.reply(
        f"🎉 گربه‌ی جدید گرفتی!\n"
        f"ID: <code>{cat_id}</code>\n"
        f"rarity: {rarity}\n"
        f"میوپوینت باقی‌مانده: <b>{new_points}</b>"
    )


@dp.message_handler(commands=["feed"])
async def cmd_feed(message: types.Message):
    user_id, _ = get_or_create_user(message.from_user.id, message.from_user.username)
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("استفاده: /feed <cat_id> <amount>")
        return

    try:
        cat_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await message.reply("cat_id و amount باید عدد باشن.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("چنین گربه‌ای برای تو پیدا نشد.")
        return

    now = int(time.time())
    cat = compute_cat_state(cat, now)

    if not cat.get("is_alive", True):
        await message.reply("این گربه متاسفانه مرده 💀 و نمی‌شه بهش غذا داد.")
        return

    if amount <= 0:
        await message.reply("مقدار غذا باید مثبت باشه.")
        return

    hunger = cat.get("hunger", 0)
    overfeed_strikes = cat.get("overfeed_strikes", 0)
    is_sick = cat.get("is_sick", False)

    # اگر گربه از قبل خیلی سیره
    if hunger >= 100:
        if overfeed_strikes < 2:
            overfeed_strikes += 1
            update_cat_fields(cat_id, user_id, {
                "overfeed_strikes": overfeed_strikes,
                "last_tick_ts": now,
            })
            await message.reply("گربه‌ات کاملاً سیره و مقاومت می‌کنه 😾 (overfeed warning)")
            return
        elif overfeed_strikes == 2:
            # مریض می‌شه
            overfeed_strikes += 1
            is_sick = True
            update_cat_fields(cat_id, user_id, {
                "overfeed_strikes": overfeed_strikes,
                "is_sick": True,
                "last_tick_ts": now,
            })
            await message.reply("از بس غذا چپوندی، گربه‌ات مریض شد 🤢 مراقبش باش.")
            return
        else:
            # مرگ ناشی از overfeed
            update_cat_fields(cat_id, user_id, {
                "is_alive": False,
                "death_ts": now,
                "last_tick_ts": now,
            })
            await message.reply("گربه‌ات از بس overfeed شد، مُرد 💀")
            return

    # حالت عادی
    new_hunger = min(100, hunger + amount)

    # اگر خیلی پر شد، یک strike اضافه
    if new_hunger >= 100 and hunger < 100:
        overfeed_strikes = min(3, overfeed_strikes + 1)

    update_cat_fields(cat_id, user_id, {
        "hunger": new_hunger,
        "overfeed_strikes": overfeed_strikes,
        "last_tick_ts": now,
    })

    await message.reply(f"🍽 گربه‌ات سیر شد! گرسنگی جدید: {new_hunger}/100")


@dp.message_handler(commands=["play"])
async def cmd_play(message: types.Message):
    user_id, _ = get_or_create_user(message.from_user.id, message.from_user.username)
    args = message.get_args().split()
    if len(args) != 1:
        await message.reply("استفاده: /play <cat_id>")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("cat_id باید عدد باشه.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("چنین گربه‌ای برای تو پیدا نشد.")
        return

    now = int(time.time())
    cat = compute_cat_state(cat, now)

    if not cat.get("is_alive", True):
        await message.reply("این گربه مرده 💀 و دیگه بازی نمی‌کنه.")
        return

    if cat.get("is_sick"):
        await message.reply("گربه‌ات مریضه 🤢 و حال بازی کردن نداره.")
        return

    hunger = cat.get("hunger", 0)
    happiness = cat.get("happiness", 0)
    level = cat.get("level", 1)
    xp = cat.get("xp", 0)

    # بازی کردن کمی گرسنه‌تر می‌کنه ولی خوشحال‌تر
    hunger = max(0, hunger - 5)
    happiness = min(100, happiness + 15)
    level, xp = get_level_and_xp_after_gain(level, xp, 20)

    update_cat_fields(cat_id, user_id, {
        "hunger": hunger,
        "happiness": happiness,
        "level": level,
        "xp": xp,
        "last_tick_ts": now,
    })

    # پیام متنی
    text = (
        f"😺 گربه‌ات حسابی بازی کرد!\n"
        f"سطح: {level}, XP: {xp}/100\n"
        f"گرسنگی: {hunger}/100 | خوشحالی: {happiness}/100"
    )

    if PLAY_GIFS:
        await bot.send_animation(
            chat_id=message.chat.id,
            animation=random.choice(PLAY_GIFS),
            caption=text,
        )
    else:
        await message.reply(text)


@dp.message_handler(commands=["rename"])
async def cmd_rename(message: types.Message):
    user_id, _ = get_or_create_user(message.from_user.id, message.from_user.username)
    args = message.get_args().split(maxsplit=1)
    if len(args) != 2:
        await message.reply("استفاده: /rename <cat_id> <اسم جدید>")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("cat_id باید عدد باشه.")
        return

    new_name = args[1].strip()
    if not new_name:
        await message.reply("اسم جدید نباید خالی باشه.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("چنین گربه‌ای برای تو پیدا نشد.")
        return

    rename_cat(user_id, cat_id, new_name)
    await message.reply(f"اسم گربه با ID <code>{cat_id}</code> شد: {quote_html(new_name)}")


@dp.message_handler(commands=["style"])
async def cmd_style(message: types.Message):
    user_id, _ = get_or_create_user(message.from_user.id, message.from_user.username)
    args = message.get_args().split(maxsplit=1)
    if len(args) != 2:
        await message.reply("استفاده: /style <cat_id> <توضیح ظاهر>")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("cat_id باید عدد باشه.")
        return

    appearance = args[1].strip()
    if not appearance:
        await message.reply("توضیح ظاهر نباید خالی باشه.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("چنین گربه‌ای برای تو پیدا نشد.")
        return

    update_cat_appearance(user_id, cat_id, appearance)
    await message.reply("ظاهر گربه‌ات آپدیت شد 😺")


@dp.message_handler(commands=["transfer"])
async def cmd_transfer(message: types.Message):
    user_id, user_row = get_or_create_user(message.from_user.id, message.from_user.username)
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("استفاده: /transfer <cat_id> @username")
        return

    try:
        cat_id = int(args[0])
    except ValueError:
        await message.reply("cat_id باید عدد باشه.")
        return

    target_mention = args[1]
    if not target_mention.startswith("@"):
        await message.reply("لطفاً یوزرنیم مقصد را با @ بنویس.")
        return

    # ما از Telegram API target را مستقیم نمی‌گیریم؛ فقط اجازه می‌دیم دستی یوزرنیم را تایپ کنند
    # برای ساده‌سازی: تا وقتی اون یوزر یک بار با بات کار نکرده، نمی‌تونه گیرنده باشد.
    current_points = user_row.get("mew_points", 0)
    if current_points < TRANSFER_COST:
        await message.reply(f"برای انتقال گربه حداقل {TRANSFER_COST} میوپوینت لازم داری.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("چنین گربه‌ای برای تو پیدا نشد.")
        return

    # ما یوزر مقصد را از روی یوزرنیم توی DB پیدا نمی‌کنیم
    # به جای این، می‌گیم مقصد باید یک بار /start را در PV بزند و ID داخلی‌اش را بهت بده
    # برای الان یک نسخه ساده: فقط با ریپلای روی پیام شخص در گروه، راحت‌تر می‌شد، ولی فعلاً:
    await message.reply(
        "برای نسخه فعلی، انتقال فقط وقتی ممکنه که ID داخلی مقصد رو بدونی.\n"
        "این بخش رو بعداً می‌تونیم بهتر کنیم (مثلاً با ریپلای روی پیام طرف در گروه)."
    )
    # ساده‌تر: فعلاً این قسمت رو غیرفعال کنیم تا بازی‌ خراب نشه
    # اگر خواستی واقعاً transfer واقعی بسازیم (با reply) بگو تا نسخه کاملش رو بنویسم.
    return


@dp.message_handler(commands=["leaderboard"])
async def cmd_leaderboard(message: types.Message):
    rows = get_leaderboard(limit=10)
    if not rows:
        await message.reply("هنوز کسی امتیازی نگرفته.")
        return

    lines = ["🏆 لیدربورد میولند:\n"]
    for i, row in enumerate(rows, start=1):
        username = row.get("username") or f"#{row.get('telegram_id')}"
        mp = row.get("mew_points", 0)
        lines.append(f"{i}. {username} — {mp} میوپوینت")

    await message.reply("\n".join(lines))


# ---------- هندلر MEW (کسب امتیاز) ----------

@dp.message_handler(lambda m: m.text and m.text.strip().lower() == "mew")
async def handle_mew(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        # فقط توی گروه امتیاز می‌ده
        return

    await maybe_trigger_event(message)  # احتمال شروع رویداد
    # خودش پیام mew هم می‌تونه برای event جواب باشه
    await handle_event_reply(message)

    user_id, user_row = get_or_create_user(message.from_user.id, message.from_user.username)
    register_user_group(user_id, message.chat.id)

    now = int(time.time())
    last_mew = user_row.get("last_mew_ts")

    if last_mew:
        diff = now - int(last_mew)
        if diff < MEW_COOLDOWN:
            remain = MEW_COOLDOWN - diff
            mins = remain // 60
            secs = remain % 60
            await message.reply(
                f"هنوز باید {mins} دقیقه و {secs} ثانیه صبر کنی تا دوباره میو بزنی 😼"
            )
            return

    current_points = user_row.get("mew_points", 0)
    new_points = current_points + 1

    update_user_mew(message.from_user.id, mew_points=new_points, last_mew_ts=now)
    await message.reply(f"مـیــو! 😺\nامتیاز جدیدت: <b>{new_points}</b> میوپوینت")


# ---------- هندلر عمومی پیام‌های متنی برای ایونت‌ها ----------

@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_all_text(message: types.Message):
    # این هندلر آخر اجرا می‌شود (بعد از بقیه فیلترها)
    if message.chat.type in ("group", "supergroup"):
        await maybe_trigger_event(message)
        await handle_event_reply(message)


# ---------- هندلر سراسری ارورها ----------

@dp.errors_handler()
async def global_error_handler(update, error):
    logger.exception("Unhandled error: %r", error)
    try:
        await bot.send_message(ADMIN_ID, f"❌ Error: {repr(error)}")
    except Exception:
        pass
    # خطا را مصرف کن که دیگه بالاتر نره
    return True


# ---------- Webhook / Aiohttp ----------

async def handle_webhook(request: web.Request):
    token = request.match_info.get("token")
    if token != BOT_TOKEN:
        return web.Response(status=403, text="Forbidden")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Bad request")

    from aiogram import types as tg_types
    # این دو خط مهم هستند تا message.reply و ... bot را بشناسند
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    update = tg_types.Update(**data)
    try:
        await dp.process_update(update)
    except Exception as e:
        logger.exception("Error while processing update: %r", e)
        try:
            await bot.send_message(ADMIN_ID, f"❌ Webhook error: {repr(e)}")
        except Exception:
            pass

    return web.Response(text="OK")


async def handle_root(request: web.Request):
    return web.Response(text="Mewland bot is alive 🐱")


async def on_startup(app: web.Application):
    init_db()
    if APP_URL:
        url = APP_URL.rstrip("/") + f"/webhook/{BOT_TOKEN}"
        try:
            await bot.set_webhook(url)
            logger.info("Webhook set to %s", url)
        except TelegramAPIError as e:
            logger.exception("Failed to set webhook: %r", e)
    else:
        logger.warning("APP_URL/RENDER_EXTERNAL_URL ست نشده؛ webhook ممکن است درست کار نکند.")


async def on_shutdown(app: web.Application):
    try:
        await bot.delete_webhook()
        logger.info("Webhook deleted")
    except TelegramAPIError:
        pass
    await bot.session.close()


def create_app():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_post("/webhook/{token}", handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


def main():
    app = create_app()
    web.run_app(app, host=APP_HOST, port=APP_PORT)


if __name__ == "__main__":
    main()
