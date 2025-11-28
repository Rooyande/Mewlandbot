# bot.py
import os
import logging
import random
import time
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils import executor

from db import (
    init_db,
    get_or_create_user,
    get_user,
    update_user_mew,
    register_user_group,
    get_group_users,
    get_all_users,
    get_user_cats,
    add_cat,
    get_cat,
    update_cat_stats,
)

# ---------------- تنظیمات اصلی ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # از Render ست می‌کنی

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is not set")

MEW_COOLDOWN_SECONDS = 7 * 60   # کول‌داون میو
MEW_REWARD = 10                 # امتیاز هر میو
CAT_COST = 100                  # هزینه‌ی گرفتن گربه

TICK_HOURS = 3                  # هر ۳ ساعت یک تیک
TICK_SECONDS = TICK_HOURS * 3600

# rarity و احتمال
RARITIES = [
    ("Common",   0.55),
    ("Uncommon", 0.25),
    ("Rare",     0.12),
    ("Epic",     0.06),
    ("Mythical", 0.015),
    ("Cosmic",   0.005),
]

RARITY_WEIGHTS = {
    "Common":   1,
    "Uncommon": 2,
    "Rare":     4,
    "Epic":     8,
    "Mythical": 15,
    "Cosmic":   30,
}

ELEMENT_BONUS = {
    "Street": 1.0,
    "Flame":  1.1,
    "Shadow": 1.1,
    "Nature": 1.0,
    "Royal":  1.2,
    "Cosmic": 1.3,
}

ELEMENT_FA = {
    "Street": "خیابانی",
    "Flame":  "آتیشی",
    "Shadow": "سایه‌ای",
    "Nature": "طبیعتی",
    "Royal":  "سلطنتی",
    "Cosmic": "کیهانی",
}

TRAITS = [
    "خوابالو",
    "کیبوردنَشین",
    "گلدون‌سقّاط‌کن",
    "موش‌باز حرفه‌ای",
    "ضد جاروبرقی",
    "گنگستر محله",
    "خجالتی و دل‌نازک",
    "پررو و بامزه",
]

ADJECTIVES = [
    "خوابالو",
    "افسانه‌ای",
    "بدقلق",
    "خیلی اجتماعی",
    "دیوانه‌وار پرانرژی",
    "خفن و مرموز",
]

HABITS = [
    "روی کیبورد می‌خوابد",
    "نیمه‌شب روی پشت‌بام آواز می‌خواند",
    "پلاستیک گاز می‌زند",
    "هرچی روی میز است را هل می‌دهد پایین",
    "روی گوشی‌ات می‌نشیند وقتی لازمش داری",
]

FEARS = [
    "جاروبرقی",
    "آدم‌هایی که می‌گویند سگ از گربه بهتر است",
    "دوش حمام",
    "درِ بستهٔ یخچال",
]

# eventهای تیک ۳ ساعته
TICK_EVENTS = [
    {
        "text": "یک موش شکار کرد و کلی ذوق کرد! (+۵ XP، +۵ شادی، -۲ گرسنگی)",
        "dxp": 5,
        "dhunger": -2,
        "dhappy": 5,
        "dmew": 0,
    },
    {
        "text": "روی کیبورد خوابید و گرم شد. (+۳ XP، +۳ شادی)",
        "dxp": 3,
        "dhunger": 0,
        "dhappy": 3,
        "dmew": 0,
    },
    {
        "text": "با جاروبرقی دعوا کرد. (+۲ XP، -۵ شادی)",
        "dxp": 2,
        "dhunger": 0,
        "dhappy": -5,
        "dmew": 0,
    },
    {
        "text": "در آشپزخانه چیزی انداخت پایین! (-۳ شادی، -۱ گرسنگی)",
        "dxp": 0,
        "dhunger": -1,
        "dhappy": -3,
        "dmew": 0,
    },
]

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# ---------------- کیبورد اصلی ----------------
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add(KeyboardButton("میــــو 😺"))
main_kb.add(
    KeyboardButton("✨ گرفتن گربه"),
    KeyboardButton("🐱 گربه‌هام"),
)

# ---------------- توابع کمکی گیم ----------------
def choose_rarity():
    r = random.random()
    cumulative = 0
    for name, prob in RARITIES:
        cumulative += prob
        if r <= cumulative:
            return name
    return RARITIES[-1][0]


def generate_cat_meta():
    element = random.choice(list(ELEMENT_BONUS.keys()))
    trait = random.choice(TRAITS)
    adj = random.choice(ADJECTIVES)
    habit = random.choice(HABITS)
    fear = random.choice(FEARS)

    element_fa = ELEMENT_FA.get(element, element)

    description = (
        f"این گربه‌ی {adj} از نوع {element_fa} است که معمولاً {habit} "
        f"و از {fear} متنفر است."
    )
    return element, trait, description


def max_hunger_for_level(level: int) -> int:
    return 100 + (level - 1) * 5


def max_happiness_for_level(level: int) -> int:
    return 100 + (level - 1) * 5


def xp_needed_for_next_level(level: int) -> int:
    return level * 50


def cat_power(cat_row):
    rarity = cat_row["rarity"]
    element = cat_row["element"]
    level = cat_row["level"]
    base = RARITY_WEIGHTS.get(rarity, 1)
    bonus = ELEMENT_BONUS.get(element, 1.0)
    return int(level * base * bonus)


def format_cat(cat_row):
    cat_id = cat_row["id"]
    name = cat_row["name"]
    rarity = cat_row["rarity"]
    element = cat_row["element"]
    trait = cat_row["trait"]
    description = cat_row["description"]
    level = cat_row["level"]
    xp = cat_row["xp"]
    hunger = cat_row["hunger"]
    happiness = cat_row["happiness"]
    created_at = cat_row["created_at"]

    created_str = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M")
    element_fa = ELEMENT_FA.get(element, element)

    return (
        f"🐱 <b>{name}</b> [ID: <code>{cat_id}</code>]\n"
        f"✨ Rarity: <b>{rarity}</b> | نوع: <b>{element_fa}</b>\n"
        f"😼 خصوصیت: <i>{trait}</i>\n"
        f"📈 Level: <b>{level}</b> | XP: <b>{xp}</b> / {xp_needed_for_next_level(level)}\n"
        f"🍗 Hunger: <b>{hunger}/{max_hunger_for_level(level)}</b>\n"
        f"🎮 Happiness: <b>{happiness}/{max_happiness_for_level(level)}</b>\n"
        f"📅 Created: <i>{created_str}</i>\n\n"
        f"🧾 توضیح:\n{description}"
    )


def cat_inline_kb(cat_id):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🍗 غذا دادن", callback_data=f"feed:{cat_id}"))
    # بعداً می‌تونی اینا رو اضافه کنی:
    # kb.add(InlineKeyboardButton("🎲 بازی", callback_data=f"play:{cat_id}"))
    # kb.add(InlineKeyboardButton("🧳 کار", callback_data=f"job:{cat_id}"))
    return kb


def ensure_user_and_group(message: types.Message):
    """ثبت یوزر و اگر گروه بود، ثبت گروه برای لیدربورد"""
    user_telegram_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(user_telegram_id, username)

    if message.chat.type in ("group", "supergroup"):
        register_user_group(user_id, message.chat.id)

    return user_id


def process_cat_ticks(cat_row, user_row):
    """
    شبیه‌سازی تیک‌های ۳ ساعته برای یک گربه، وقتی یوزر برمی‌گرده و گربه رو نگاه می‌کنه.
    هم استت گربه آپدیت می‌شه، هم ممکنه XP و غیره عوض بشه.
    """
    now = int(time.time())
    last_tick = cat_row["last_tick_ts"] or cat_row["created_at"]

    delta = now - last_tick
    ticks = delta // TICK_SECONDS

    if ticks <= 0:
        return cat_row, "", user_row  # هیچ اتفاقی

    hunger = cat_row["hunger"]
    happiness = cat_row["happiness"]
    xp = cat_row["xp"]
    level = cat_row["level"]

    mew_points = user_row["mew_points"]
    last_mew_ts = user_row["last_mew_ts"]

    events_text = []

    for _ in range(int(ticks)):
        # افت طبیعی
        hunger -= 5
        happiness -= 3

        # event تصادفی با احتمال ۴۰٪
        if random.random() < 0.4:
            ev = random.choice(TICK_EVENTS)
            xp += ev["dxp"]
            hunger += ev["dhunger"]
            happiness += ev["dhappy"]
            mew_points += ev["dmew"]
            events_text.append(ev["text"])

        # لول‌آپ در صورت نیاز
        while xp >= xp_needed_for_next_level(level):
            xp -= xp_needed_for_next_level(level)
            level += 1

        # محدود کردن استت‌ها
        max_h = max_hunger_for_level(level)
        max_hp = max_happiness_for_level(level)

        hunger = max(0, min(max_h, hunger))
        happiness = max(0, min(max_hp, happiness))
        xp = max(0, xp)

    # ذخیره در دیتابیس
    update_user_mew(user_row["telegram_id"], mew_points, last_mew_ts)
    update_cat_stats(cat_row["id"], cat_row["owner_id"], hunger, happiness, xp, level, now)

    # دوباره از دیتابیس بخونیم تا مقدار نهایی دقیق باشد
    new_user = get_user(user_row["telegram_id"])
    new_cat = get_cat(cat_row["id"], cat_row["owner_id"])

    extra_text = ""
    if events_text:
        extra_text = "📜 در این مدت که نبودی:\n" + "\n".join("• " + t for t in events_text)

    return new_cat, extra_text, new_user


# ---------------- هندلرها ----------------
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    ensure_user_and_group(message)

    if message.chat.type == "private":
        await message.answer(
            "به <b>میولند</b> خوش اومدی! 🐾\n"
            "اینجا می‌تونی با «میو» کردن، میوپوینت جمع کنی، گربه بگیری، بزرگش کنی و باهاش زندگی کنی.\n\n"
            "✅ از گروه‌ها هم می‌تونی استفاده کنی، فقط بات رو به گروه اضافه کن و میو کن!\n\n"
            "دکمه‌های پایین رو بزن و شروع کن:",
            reply_markup=main_kb,
        )
    else:
        await message.answer(
            "من بات گربه‌های <b>میولند</b> هستم 😺\n"
            "اینجا توی گروه هم می‌تونی «میو» کنی و گربه بگیری.\n"
            "برای مدیریت کامل کالکشن گربه‌هات، می‌تونی بهم توی پی‌وی هم /start بدی."
        )


@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await message.answer(
        "راهنمای کوتاه میولند 🐾\n\n"
        "/start – شروع و ثبت‌نام\n"
        "/adopt – اگر میوپوینت کافی داشته باشی، یک گربه جدید می‌گیری\n"
        "/cats – لیست گربه‌هات\n"
        "/cat_1 – جزئیات گربه با ID=1\n"
        "/top – لیدربورد همین گروه بر اساس قدرت گربه‌ها\n"
        "/top_global – لیدربورد جهانی\n\n"
        "یا از دکمه‌های «میــــو 😺»، «✨ گرفتن گربه» و «🐱 گربه‌هام» استفاده کن."
    )


@dp.message_handler(lambda m: m.text and m.text.strip() in ["میو", "meow", "Meow", "میــــو 😺"])
async def handle_mew(message: types.Message):
    ensure_user_and_group(message)

    u = get_user(message.from_user.id)
    if not u:
        get_or_create_user(message.from_user.id, message.from_user.username)
        u = get_user(message.from_user.id)

    mew_points = u["mew_points"]
    last_mew_ts = u["last_mew_ts"]
    now = int(time.time())

    if last_mew_ts is not None and now - last_mew_ts < MEW_COOLDOWN_SECONDS:
        remaining = MEW_COOLDOWN_SECONDS - (now - last_mew_ts)
        mins = remaining // 60
        secs = remaining % 60
        await message.reply(
            f"هنوز زوده برای میو بعدی 😼\n"
            f"⏳ مونده: {mins:02d}:{secs:02d}"
        )
        return

    mew_points += MEW_REWARD
    update_user_mew(message.from_user.id, mew_points, now)

    await message.reply(
        f"میــــو! 😺\n"
        f"+{MEW_REWARD} میوپوینت گرفتی.\n"
        f"مجموع: <b>{mew_points}</b> میوپوینت.",
        reply_markup=(main_kb if message.chat.type == "private" else None),
    )


@dp.message_handler(commands=["adopt"])
async def cmd_adopt(message: types.Message):
    await handle_get_cat(message)


@dp.message_handler(lambda m: m.text == "✨ گرفتن گربه")
async def handle_get_cat(message: types.Message):
    ensure_user_and_group(message)

    u = get_user(message.from_user.id)
    if not u:
        await message.answer("اول /start رو بزن تا ثبت‌نام بشی.")
        return

    user_id = u["id"]
    mew_points = u["mew_points"]
    last_mew_ts = u["last_mew_ts"]

    if mew_points < CAT_COST:
        await message.answer(
            f"برای گرفتن گربه حداقل <b>{CAT_COST}</b> میوپوینت می‌خوای.\n"
            f"الان فقط <b>{mew_points}</b> تا داری 😿"
        )
        return

    mew_points -= CAT_COST
    update_user_mew(message.from_user.id, mew_points, last_mew_ts)

    rarity = choose_rarity()
    element, trait, description = generate_cat_meta()
    name = random.choice(["میشی", "پیشی", "هیسکو", "لولیتا", "موچو", "خرخری", "نِکو"])

    cat_id = add_cat(user_id, name, rarity, element, trait, description)
    cat = get_cat(cat_id, user_id)

    text = (
        f"🎉 <b>یه گربهٔ جدید گرفتی!</b>\n\n"
        f"{format_cat(cat)}\n\n"
        f"میوپوینت باقی‌مونده: <b>{mew_points}</b>"
    )

    await message.answer(
        text,
        reply_markup=(main_kb if message.chat.type == "private" else None),
    )


@dp.message_handler(commands=["cats"])
async def cmd_cats(message: types.Message):
    ensure_user_and_group(message)

    u = get_user(message.from_user.id)
    if not u:
        await message.answer("اول /start رو بزن تا ثبت‌نام بشی.")
        return

    user_id = u["id"]
    cats = get_user_cats(user_id)

    if not cats:
        await message.answer(
            "هنوز هیچ گربه‌ای نداری 😿\n"
            "با «✨ گرفتن گربه» یکی بیار خونه‌ت."
        )
        return

    lines = []
    for cat in cats[:20]:
        power = cat_power(cat)
        lines.append(
            f"ID <code>{cat['id']}</code> — 🐱 <b>{cat['name']}</b> "
            f"({cat['rarity']}, {ELEMENT_FA.get(cat['element'], cat['element'])}) "
            f"| Lv.{cat['level']} | Power: {power}"
        )

    text = "🐾 گربه‌های تو:\n\n" + "\n".join(lines)
    text += "\n\nبرای دیدن جزئیات یک گربه، /cat_ID رو بفرست (مثلاً /cat_1)"

    await message.answer(text)


@dp.message_handler(lambda m: m.text and m.text.startswith("/cat_"))
async def handle_cat_command(message: types.Message):
    ensure_user_and_group(message)

    try:
        cat_id = int(message.text.split("_", 1)[1])
    except Exception:
        await message.answer("فرمت درست: /cat_<id> مثلاً /cat_1")
        return

    u = get_user(message.from_user.id)
    if not u:
        await message.answer("اول /start رو بزن تا ثبت‌نام بشی.")
        return

    user_id = u["id"]
    cat = get_cat(cat_id, user_id)
    if not cat:
        await message.answer("چنین گربه‌ای برای تو پیدا نشد 😿")
        return

    # شبیه‌سازی تیک‌های ۳ ساعته قبل از نمایش
    cat, extra, new_user = process_cat_ticks(cat, u)

    msg = format_cat(cat)
    if extra:
        msg += "\n\n" + extra

    await message.answer(msg, reply_markup=cat_inline_kb(cat_id))


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("feed:"))
async def handle_feed_cat(callback_query: types.CallbackQuery):
    cat_id = int(callback_query.data.split(":")[1])

    u = get_user(callback_query.from_user.id)
    if not u:
        await callback_query.answer("اول /start رو بزن.", show_alert=True)
        return

    user_id = u["id"]
    mew_points = u["mew_points"]
    last_mew_ts = u["last_mew_ts"]

    cat = get_cat(cat_id, user_id)
    if not cat:
        await callback_query.answer("این گربه مال تو نیست!", show_alert=True)
        return

    # قبل از غذا دادن، تیک‌های ۳ ساعته را اعمال کن
    cat, extra, u_after_ticks = process_cat_ticks(cat, u)
    mew_points = u_after_ticks["mew_points"]
    last_mew_ts = u_after_ticks["last_mew_ts"]

    if mew_points < 5:
        await callback_query.answer("میوپوینتت برای غذا دادن کمه (حداقل ۵).", show_alert=True)
        return

    mew_points -= 5

    level = cat["level"]
    hunger = cat["hunger"]
    happiness = cat["happiness"]
    xp = cat["xp"]

    max_h = max_hunger_for_level(level)
    max_hp = max_happiness_for_level(level)

    hunger = min(max_h, hunger + 20)
    happiness = min(max_hp, happiness + 10)
    xp += 5

    # لِوِل‌آپ
    while xp >= xp_needed_for_next_level(level):
        xp -= xp_needed_for_next_level(level)
        level += 1
        max_h = max_hunger_for_level(level)
        max_hp = max_happiness_for_level(level)

    update_user_mew(callback_query.from_user.id, mew_points, last_mew_ts)
    update_cat_stats(cat_id, user_id, hunger, happiness, xp, level, int(time.time()))

    updated_cat = get_cat(cat_id, user_id)

    text = format_cat(updated_cat)
    if extra:
        text += "\n\n" + extra

    await callback_query.message.edit_text(
        text,
        reply_markup=cat_inline_kb(cat_id),
    )
    await callback_query.answer("🍗 گربه‌ت غذا خورد و خوشحال‌تر شد!")


@dp.message_handler(commands=["top"])
async def cmd_top(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("این کامند برای لیدربورد گروه است، توی یک گروه امتحانش کن 😺")
        return

    ensure_user_and_group(message)

    chat_id = message.chat.id
    users = get_group_users(chat_id)

    if not users:
        await message.answer("تو این گروه هنوز کسی ثبت نشده 😿\nاول چند نفر /start بزنن یا میو کنن.")
        return

    scores = []
    for u in users:
        cats = get_user_cats(u["id"])
        total_power = sum(cat_power(c) for c in cats)
        scores.append((u, total_power))

    scores = [s for s in scores if s[1] > 0]
    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores:
        await message.answer("کسی هنوز گربه‌ای نگرفته که قدرتی داشته باشه 😼")
        return

    lines = []
    for idx, (u, power) in enumerate(scores[:10], start=1):
        username = u["username"] or u["telegram_id"]
        lines.append(f"{idx}. <b>{username}</b> — Cat Power: <b>{power}</b>")

    text = "🏆 لیدربورد این گروه (بر اساس قدرت گربه‌ها):\n\n" + "\n".join(lines)
    await message.answer(text)


@dp.message_handler(commands=["top_global"])
async def cmd_top_global(message: types.Message):
    users = get_all_users()
    if not users:
        await message.answer("هنوز هیچ یوزری ثبت نشده 😿")
        return

    scores = []
    for u in users:
        cats = get_user_cats(u["id"])
        total_power = sum(cat_power(c) for c in cats)
        scores.append((u, total_power))

    scores = [s for s in scores if s[1] > 0]
    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores:
        await message.answer("هنوز هیچ گربه‌ای در جهان میولند احضار نشده 😼")
        return

    lines = []
    for idx, (u, power) in enumerate(scores[:10], start=1):
        username = u["username"] or u["telegram_id"]
        lines.append(f"{idx}. <b>{username}</b> — Cat Power: <b>{power}</b>")

    text = "🌍 لیدربورد جهانی میولند:\n\n" + "\n".join(lines)
    await message.answer(text)


# ---------------- اجرای اصلی ----------------
if __name__ == "__main__":
    init_db()
    executor.start_polling(dp, skip_updates=True)
