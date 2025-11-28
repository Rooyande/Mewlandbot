import os
import logging
import time
import random

from aiohttp import web
from aiogram import Bot, Dispatcher, types

from db import (
    init_db, 
    get_user,
    get_or_create_user,
    update_user_mew,
    get_all_users,
    register_user_group,
    get_group_users,
    get_user_cats,
    add_cat,
    get_cat,
    update_cat_stats,
    rename_cat,
    set_cat_owner,
    get_leaderboard,  # 👈 حتماً این باشه
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ---------- تنظیمات وبهوک / سرور ----------

# Render معمولاً RENDER_EXTERNAL_URL می‌دهد
BASE_URL = (
    os.getenv("WEBHOOK_BASE_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or "https://mewlandbot.onrender.com"
)
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = BASE_URL.rstrip("/") + WEBHOOK_PATH

APP_HOST = "0.0.0.0"
APP_PORT = int(os.getenv("PORT", "10000"))

# ---------- تنظیمات بازی ----------

MEW_COOLDOWN_SEC = 7 * 60

COST_ADOPT = 30
COST_FEED = 5
COST_PLAY = 3
COST_TRAIN = 8

XP_PER_PLAY = 5
XP_PER_TRAIN = 15

HUNGER_DECAY_PER_HOUR = 3
HAPPINESS_DECAY_PER_HOUR = 2

RARITY_WEIGHTS = [
    ("common", 60),
    ("rare", 25),
    ("epic", 10),
    ("legendary", 4),
    ("mythic", 1),
]

RARITY_ORDER = {
    "common": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
    "mythic": 5,
}

ELEMENTS = ["fire", "water", "shadow", "nature", "cosmic"]
TRAITS = ["lazy", "hyper", "greedy", "cursed", "chill", "chaotic", "sleepy", "noisy"]

CAT_NAMES = [
    "Luna",
    "Pixel",
    "Nacho",
    "Mochi",
    "Neko",
    "Shadow",
    "Pumpkin",
    "Bean",
    "Miso",
    "Zuzu",
]


# ---------- Helperها ----------

def choose_rarity() -> str:
    r = random.randint(1, 100)
    acc = 0
    for name, weight in RARITY_WEIGHTS:
        acc += weight
        if r <= acc:
            return name
    return "common"


def clamp(val, lo=0, hi=100):
    return max(lo, min(hi, val))


def apply_decay(cat: dict) -> dict:
    """
    decay بر اساس last_tick_ts
    """
    now = int(time.time())
    last = cat.get("last_tick_ts") or now
    delta_sec = max(0, now - last)
    hours = delta_sec // 3600
    if hours <= 0:
        return cat

    hunger = clamp(cat.get("hunger", 50) - HUNGER_DECAY_PER_HOUR * hours)
    happiness = clamp(cat.get("happiness", 50) - HAPPINESS_DECAY_PER_HOUR * hours)
    xp = cat.get("xp", 0)
    level = cat.get("level", 1)

    update_cat_stats(
        cat_id=cat["id"],
        owner_id=cat["owner_id"],
        hunger=hunger,
        happiness=happiness,
        xp=xp,
        level=level,
        last_tick_ts=now,
    )

    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["xp"] = xp
    cat["level"] = level
    cat["last_tick_ts"] = now
    return cat


def apply_levelup(cat: dict):
    """
    اگر xp کافی باشد، level up می‌کند.
    """
    leveled = False
    old_level = cat.get("level", 1)
    xp = cat.get("xp", 0)
    level = old_level

    while True:
        xp_needed = level * 20
        if xp >= xp_needed:
            xp -= xp_needed
            level += 1
            leveled = True
        else:
            break

    if leveled:
        now = int(time.time())
        update_cat_stats(
            cat_id=cat["id"],
            owner_id=cat["owner_id"],
            hunger=cat.get("hunger", 50),
            happiness=cat.get("happiness", 50),
            xp=xp,
            level=level,
            last_tick_ts=now,
        )
        cat["xp"] = xp
        cat["level"] = level
        cat["last_tick_ts"] = now

    return leveled, old_level, cat.get("level", old_level)


def format_cat(cat: dict) -> str:
    return (
        f"🐱 {cat['name']} #{cat['id']}\n"
        f"rarity: {cat['rarity']} | element: {cat['element']} | trait: {cat['trait']}\n"
        f"level: {cat.get('level', 1)} (xp: {cat.get('xp', 0)})\n"
        f"hunger: {cat.get('hunger', 0)}/100 | happiness: {cat.get('happiness', 0)}/100\n"
        f"desc: {cat.get('description', '')}"
    )


def parse_cat_id_from_message(message: types.Message) -> int | None:
    parts = message.text.strip().split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


# ---------- Command Handlers ----------

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    if message.chat.type in ("group", "supergroup"):
        register_user_group(user_id, message.chat.id)

    text = (
        "به مِولَند خوش اومدی 😼\n\n"
        "هر ۷ دقیقه یک‌بار تو گروه بنویس `mew` تا میوپوینت بگیری.\n"
        "با `/adopt` می‌تونی اولین گربه‌تو بگیری.\n"
        "با `/mycats` گربه‌هات رو ببین، و با `/leaderboard` ببین کی خفن‌تره."
    )
    await message.reply(text, parse_mode="Markdown")


@dp.message_handler(commands=["profile"])
async def cmd_profile(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    user_row = get_user(tg_id)
    cats = get_user_cats(user_id)
    mew_points = user_row.get("mew_points", 0) if user_row else 0
    num_cats = len(cats)

    rarest = None
    for c in cats:
        if rarest is None:
            rarest = c
        else:
            if RARITY_ORDER.get(c["rarity"], 0) > RARITY_ORDER.get(rarest["rarity"], 0):
                rarest = c

    uname_display = "@" + username if username else f"user_{tg_id}"

    text = f"👤 پروفایل {uname_display}\n\n"
    text += f"میوپوینت: {mew_points}\n"
    text += f"تعداد گربه‌ها: {num_cats}\n"

    if rarest:
        text += (
            "\n✨ Rareترین گربه:\n"
            f"{rarest['name']} (#{rarest['id']}) – {rarest['rarity']} / {rarest['element']} / lvl {rarest.get('level', 1)}"
        )
    else:
        text += "\nهنوز هیچ گربه‌ای نداری. با /adopt یکی بگیر 😺"

    await message.reply(text)


@dp.message_handler(commands=["mycats"])
async def cmd_mycats(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    cats = get_user_cats(user_id)
    if not cats:
        await message.reply("هنوز هیچ گربه‌ای نداری! با /adopt یکی بگیر 😺")
        return

    lines = []
    for c in cats:
        lines.append(
            f"#{c['id']} – {c['name']} | ⭐ {c['rarity']} | lvl {c.get('level', 1)} | 😋 {c.get('hunger', 0)} | 😊 {c.get('happiness', 0)}"
        )

    text = "🐱 گربه‌هات:\n" + "\n".join(lines)
    await message.reply(text)


@dp.message_handler(commands=["adopt"])
async def cmd_adopt(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    user_row = get_user(tg_id)
    mew_points = user_row.get("mew_points", 0) if user_row else 0

    if mew_points < COST_ADOPT:
        await message.reply(f"برای گرفتن گربه جدید حداقل {COST_ADOPT} میوپوینت لازم داری. الان: {mew_points}")
        return

    rarity = choose_rarity()
    element = random.choice(ELEMENTS)
    trait = random.choice(TRAITS)
    name = random.choice(CAT_NAMES)
    desc = f"a {rarity} {element} cat that is {trait}"

    new_cat_id = add_cat(
        owner_id=user_id,
        name=name,
        rarity=rarity,
        element=element,
        trait=trait,
        description=desc,
    )

    update_user_mew(tg_id, mew_points=mew_points - COST_ADOPT)

    cat = get_cat(new_cat_id, owner_id=user_id)
    text = "🎉 یه گربه‌ی جدید گرفتی!\n\n" + format_cat(cat)
    await message.reply(text)


@dp.message_handler(commands=["cat"])
async def cmd_cat(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    cat_id = parse_cat_id_from_message(message)
    if cat_id is None:
        await message.reply("استفاده: `/cat <id>`", parse_mode="Markdown")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("چنین گربه‌ای با این id و به مالکیت تو پیدا نشد.")
        return

    cat = apply_decay(cat)
    text = format_cat(cat)
    await message.reply(text)


@dp.message_handler(commands=["feed"])
async def cmd_feed(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    cat_id = parse_cat_id_from_message(message)
    if cat_id is None:
        await message.reply("استفاده: `/feed <id>`", parse_mode="Markdown")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("این گربه مال تو نیست یا وجود نداره.")
        return

    cat = apply_decay(cat)

    if cat.get("hunger", 0) >= 90:
        await message.reply("این گربه الان خیلی سیره، بعداً بهش غذا بده 😸")
        return

    user_row = get_user(tg_id)
    mew_points = user_row.get("mew_points", 0) if user_row else 0
    if mew_points < COST_FEED:
        await message.reply(f"برای غذا دادن {COST_FEED} میوپوینت لازم داری. الان: {mew_points}")
        return

    new_mew = mew_points - COST_FEED
    update_user_mew(tg_id, mew_points=new_mew)

    hunger = clamp(cat.get("hunger", 0) + 20)
    happiness = clamp(cat.get("happiness", 0) + 5)
    xp = cat.get("xp", 0)
    level = cat.get("level", 1)
    now = int(time.time())

    update_cat_stats(cat["id"], user_id, hunger, happiness, xp, level, now)
    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["xp"] = xp
    cat["level"] = level
    cat["last_tick_ts"] = now

    await message.reply(
        f"به {cat['name']} غذا دادی! 😋\n"
        f"hunger: {hunger}/100 | happiness: {happiness}/100\n"
        f"میوپوینت باقی‌مونده: {new_mew}"
    )


@dp.message_handler(commands=["play"])
async def cmd_play(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    cat_id = parse_cat_id_from_message(message)
    if cat_id is None:
        await message.reply("استفاده: `/play <id>`", parse_mode="Markdown")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("این گربه مال تو نیست یا وجود نداره.")
        return

    cat = apply_decay(cat)

    if cat.get("happiness", 0) >= 90:
        await message.reply("الان خیلی خوشحاله، یه ذره استراحت بدیم 😺")
        return

    user_row = get_user(tg_id)
    mew_points = user_row.get("mew_points", 0) if user_row else 0
    if mew_points < COST_PLAY:
        await message.reply(f"برای بازی کردن {COST_PLAY} میوپوینت لازم داری. الان: {mew_points}")
        return

    new_mew = mew_points - COST_PLAY
    update_user_mew(tg_id, mew_points=new_mew)

    hunger = clamp(cat.get("hunger", 0) - 5)
    happiness = clamp(cat.get("happiness", 0) + 15)
    xp = cat.get("xp", 0) + XP_PER_PLAY
    level = cat.get("level", 1)
    now = int(time.time())

    update_cat_stats(cat["id"], user_id, hunger, happiness, xp, level, now)
    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["xp"] = xp
    cat["level"] = level
    cat["last_tick_ts"] = now

    leveled, old_level, new_level = apply_levelup(cat)

    text = (
        f"با {cat['name']} بازی کردی! 🎾\n"
        f"hunger: {hunger}/100 | happiness: {happiness}/100 | xp: {cat['xp']}\n"
        f"میوپوینت باقی‌مونده: {new_mew}"
    )
    if leveled:
        text += f"\n\n🎉 {cat['name']} از lvl {old_level} رفت lvl {new_level}!"

    await message.reply(text)


@dp.message_handler(commands=["train"])
async def cmd_train(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    cat_id = parse_cat_id_from_message(message)
    if cat_id is None:
        await message.reply("استفاده: `/train <id>`", parse_mode="Markdown")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("این گربه مال تو نیست یا وجود نداره.")
        return

    cat = apply_decay(cat)

    user_row = get_user(tg_id)
    mew_points = user_row.get("mew_points", 0) if user_row else 0
    if mew_points < COST_TRAIN:
        await message.reply(f"برای تمرین {COST_TRAIN} میوپوینت لازم داری. الان: {mew_points}")
        return

    new_mew = mew_points - COST_TRAIN
    update_user_mew(tg_id, mew_points=new_mew)

    hunger = clamp(cat.get("hunger", 0) - 10)
    happiness = clamp(cat.get("happiness", 0) + 5)
    xp = cat.get("xp", 0) + XP_PER_TRAIN
    level = cat.get("level", 1)
    now = int(time.time())

    update_cat_stats(cat["id"], user_id, hunger, happiness, xp, level, now)
    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["xp"] = xp
    cat["level"] = level
    cat["last_tick_ts"] = now

    leveled, old_level, new_level = apply_levelup(cat)

    text = (
        f"{cat['name']} رو تمرین دادی! 💪\n"
        f"hunger: {hunger}/100 | happiness: {happiness}/100 | xp: {cat['xp']}\n"
        f"میوپوینت باقی‌مونده: {new_mew}"
    )
    if leveled:
        text += f"\n\n🎉 {cat['name']} از lvl {old_level} رفت lvl {new_level}!"

    await message.reply(text)


@dp.message_handler(commands=["rename"])
async def cmd_rename(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("استفاده: `/rename <id> <name>`", parse_mode="Markdown")
        return

    try:
        cat_id = int(parts[1])
    except ValueError:
        await message.reply("id گربه باید عدد باشد.")
        return

    new_name = parts[2].strip()
    if not new_name or len(new_name) > 32:
        await message.reply("اسم جدید باید ۱ تا ۳۲ کاراکتر باشد.")
        return

    cat = get_cat(cat_id, owner_id=user_id)
    if not cat:
        await message.reply("این گربه مال تو نیست یا وجود ندارد.")
        return

    rename_cat(user_id, cat_id, new_name)
    await message.reply(f"اسم گربه #{cat_id} شد: {new_name}")


@dp.message_handler(commands=["gift"])
async def cmd_gift(message: types.Message):
    """
    استفاده: جواب بده روی پیام طرف و بنویس:
    /gift <cat_id>
    """
    if not message.reply_to_message:
        await message.reply("برای هدیه دادن، باید این دستور را روی پیام کسی ریپلای کنی.")
        return

    target = message.reply_to_message.from_user
    target_tg_id = target.id
    target_username = target.username

    tg_id = message.from_user.id
    username = message.from_user.username

    from_user_id = get_or_create_user(tg_id, username)
    to_user_id = get_or_create_user(target_tg_id, target_username)

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply("استفاده: `/gift <cat_id>` به‌عنوان ریپلای روی پیام طرف.", parse_mode="Markdown")
        return

    try:
        cat_id = int(parts[1])
    except ValueError:
        await message.reply("id گربه باید عدد باشد.")
        return

    cat = get_cat(cat_id, owner_id=from_user_id)
    if not cat:
        await message.reply("این گربه مال تو نیست یا وجود ندارد.")
        return

    set_cat_owner(cat_id, to_user_id)
    await message.reply(
        f"🎁 گربه {cat['name']} (#{cat_id}) رو به {target.first_name} هدیه دادی!"
    )

@dp.message_handler(commands=["leaderboard"])
async def cmd_leaderboard(message: types.Message):
    try:
        rows = get_leaderboard(limit=10)
    except Exception as e:
        logging.exception("Error fetching leaderboard: %s", e)
        await message.reply("یه خطا تو گرفتن لیدربورد خوردیم 😿 چند دقیقه دیگه دوباره امتحان کن.")
        return

    if not rows:
        await message.reply(
            "هنوز هیچ‌کس میو نزده 😿\n"
            "اولین نفر تو باش و توی گروه فقط بنویس: mew"
        )
        return

    lines = ["🏆 لیست میوکینگ‌ها:\n"]
    for idx, row in enumerate(rows, start=1):
        username = row.get("username") or str(row.get("telegram_id", "ناشناس"))
        username = str(username)
        points = row.get("mew_points") or 0
        lines.append(f"{idx}. {username} - {points} میوپوینت")

    text = "\n".join(lines)

    try:
        await message.reply(text)  # بدون Markdown تا یوزرنیم‌های عجیب مشکل نسازن
    except Exception as e:
        logging.exception("Error sending leaderboard message: %s", e)
        await message.reply("لیدربورد آماده شد ولی تلگرام تو فرمت پیام گیر کرد 😿 بعداً دوباره امتحان کن.")


# ---------- هندلر mew ----------

@dp.message_handler(regexp=r"^mew$")
async def handle_mew(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("برای گرفتن میوپوینت، منو توی یک گروه اضافه کن 😼")
        return

    tg_id = message.from_user.id
    username = message.from_user.username
    user_id = get_or_create_user(tg_id, username)
    register_user_group(user_id, message.chat.id)

    user_row = get_user(tg_id)
    now = int(time.time())
    last = user_row.get("last_mew_ts") if user_row else None

    if last is not None:
        delta = now - last
        if delta < MEW_COOLDOWN_SEC:
            remain = MEW_COOLDOWN_SEC - delta
            mins = remain // 60
            secs = remain % 60
            await message.reply(f"هنوز باید {mins} دقیقه و {secs} ثانیه صبر کنی تا دوباره میو بزنی 😼")
            return

    mew_points = user_row.get("mew_points", 0) if user_row else 0
    gain = random.randint(3, 7)
    new_total = mew_points + gain

    update_user_mew(tg_id, mew_points=new_total, last_mew_ts=now)

    await message.reply(
        f"+{gain} میوپوینت! 🎉\n"
        f"مجموع میوپوینت‌هات: {new_total}"
    )


# ---------- Webhook / سرور ----------

async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)

    # ensure bot and dispatcher context is set
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    await dp.process_update(update)
    return web.Response()




async def index(request: web.Request):
    return web.Response(text="Mewland bot is running.")


async def on_startup(app: web.Application):
    init_db()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set to {WEBHOOK_URL}")


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    logging.info("Webhook deleted")


def main():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, host=APP_HOST, port=APP_PORT)


if __name__ == "__main__":
    main()
