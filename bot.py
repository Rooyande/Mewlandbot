# bot.py
import os
import time
import random
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.utils.exceptions import TelegramAPIError

from db import (
    get_user,
    get_or_create_user,
    update_user_mew,
    get_user_cats,
    add_cat,
    update_cat_stats,
    rename_cat,
    set_cat_owner,
    register_user_group,
    get_group_users,
    get_leaderboard,
)

# ---------- تنظیمات لاگ ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------- تنظیمات ربات و وبهوک ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

# آدرس خارجی ربات روی Render
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://mewlandbot.onrender.com")

APP_HOST = "0.0.0.0"
APP_PORT = int(os.getenv("PORT", "10000"))

WEBHOOK_PATH_TEMPLATE = "/webhook/{token}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"

OWNER_ID = 8423995337  # آی‌دی تلگرام تو برای گزارش ارورها

MEW_COOLDOWN = 7 * 60  # 7 دقیقه

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)


# ---------- helper برای فرستادن پیام به صاحب ربات ----------
async def notify_owner(text: str):
    """
    هر جا مشکلی شد، اینو صدا می‌زنیم تا ارور بیاد تو پی‌وی‌ت.
    """
    try:
        await bot.send_message(OWNER_ID, text[:4000])
    except Exception as e:
        logger.error("Failed to notify owner: %s", e)


# ---------- global error handler ----------
@dp.errors_handler()
async def global_error_handler(update: types.Update, error: Exception):
    logger.exception("Global error: %s", error)
    try:
        upd_str = str(update)[:1000] if update else "No update"
        await notify_owner(f"⚠️ Global error:\n{repr(error)}\n\nUpdate:\n{upd_str}")
    except Exception:
        pass
    # True یعنی aiogram دیگه ارور رو دوباره بالا نندازه
    return True


# ---------- چند helper گیم پلی ----------

def _format_cat(cat: dict) -> str:
    return (
        f"🐱 <b>{cat['name']}</b>\n"
        f"⭐️ سطح: <b>{cat['level']}</b>\n"
        f"✨ XP: <b>{cat['xp']}</b>\n"
        f"🍗 گرسنگی: <b>{cat['hunger']}</b>/100\n"
        f"🎮 شادی: <b>{cat['happiness']}</b>/100\n"
        f"🌈 کمیابی: <b>{cat['rarity']}</b>\n"
        f"🔥 المنت: <b>{cat['element']}</b>\n"
        f"🧬 ویژگی: <b>{cat['trait']}</b>\n"
        f"📝 توضیح: {cat['description']}"
    )


def _tick_cat_stats(cat: dict, now_ts: int) -> dict:
    """
    دگرگونی زمان برای گربه (کم شدن گرسنگی و شادی با زمان).
    """
    last = cat.get("last_tick_ts") or cat.get("created_at") or now_ts
    delta = max(0, now_ts - int(last))
    # هر 10 دقیقه مثلا 1 واحد کم بشه:
    step = delta // 600
    if step <= 0:
        return cat

    hunger = max(0, min(100, cat["hunger"] - step))
    happiness = max(0, min(100, cat["happiness"] - step))

    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["last_tick_ts"] = now_ts
    return cat


# ---------- دستورات /start ، /help ، /mypoints ----------

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        internal_id = get_or_create_user(user_id, username)

        if message.chat.type != "private":
            # ثبت اینکه این یوزر تو این گروه هست
            register_user_group(internal_id, message.chat.id)

        text = (
            "سلام 🐾\n"
            "به <b>Mewland</b> خوش اومدی!\n\n"
            "هر ۷ دقیقه یک‌بار توی گروهی که من توش هستم فقط بنویس <code>mew</code> "
            "تا میو پوینت بگیری 😼\n\n"
            "با میو پوینت‌هات می‌تونی گربه بگیری، بزرگش کنی و باهاش بازی کنی.\n\n"
            "دستورات اصلی:\n"
            "• /mypoints – دیدن میو پوینت‌هات\n"
            "• /mycats – دیدن گربه‌هات\n"
            "• /newcat – خریدن گربه جدید\n"
            "• /feed – غذا دادن به گربه\n"
            "• /play – بازی کردن با گربه\n"
            "• /rename – عوض کردن اسم گربه\n"
            "• /transfer – انتقال گربه به یک نفر دیگه\n"
            "• /leaderboard – لیدربورد میو پوینت‌ها\n"
        )
        await bot.send_message(message.chat.id, text)
    except Exception as e:
        logger.exception("Error in /start: %s", e)
        await notify_owner(f"❌ Error in /start: {repr(e)}")
        await bot.send_message(message.chat.id, "یه مشکلی پیش اومد، بعداً دوباره امتحان کن 😿")


@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    text = (
        "راهنمای Mewland 😺\n\n"
        "<b>گرفتن میو پوینت:</b>\n"
        "هر ۷ دقیقه یک‌بار توی گروه فقط بفرست <code>mew</code>.\n\n"
        "<b>دستورات:</b>\n"
        "• /mypoints – میو پوینت‌های فعلی‌ات\n"
        "• /mycats – گربه‌هات\n"
        "• /newcat – گرفتن گربه جدید (هزینه دارد)\n"
        "• /feed – غذا دادن به گربه\n"
        "• /play – بازی کردن با گربه\n"
        "• /rename – تغییر نام گربه\n"
        "• /transfer – انتقال گربه به یک پلیر دیگر\n"
        "• /leaderboard – لیدربورد جهانی\n"
    )
    await bot.send_message(message.chat.id, text)


@dp.message_handler(commands=["mypoints"])
async def cmd_mypoints(message: types.Message):
    try:
        u = get_user(message.from_user.id)
        points = u["mew_points"] if u else 0
        await bot.send_message(
            message.chat.id,
            f"🐾 میو پوینت‌های تو: <b>{points}</b>",
            reply_to_message_id=message.message_id,
        )
    except Exception as e:
        logger.exception("Error in /mypoints: %s", e)
        await notify_owner(f"❌ Error in /mypoints: {repr(e)}")
        await bot.send_message(message.chat.id, "یه مشکلی پیش اومد در گرفتن اطلاعات 😿")


# ---------- لیدربورد ----------

@dp.message_handler(commands=["leaderboard"])
async def cmd_leaderboard(message: types.Message):
    try:
        rows = get_leaderboard(limit=10)
        if not rows:
            await bot.send_message(message.chat.id, "هنوز کسی امتیاز نگرفته 😹")
            return

        lines = ["🏆 <b>لیدربورد میو پوینت‌ها</b>"]
        for i, row in enumerate(rows, start=1):
            username = row.get("username") or f"user_{row['telegram_id']}"
            points = row.get("mew_points", 0)
            lines.append(f"{i}. <b>{username}</b> – {points} میو پوینت")

        await bot.send_message(message.chat.id, "\n".join(lines))
    except Exception as e:
        logger.exception("Error fetching leaderboard: %s", e)
        await notify_owner(f"❌ Error in /leaderboard: {repr(e)}")
        await bot.send_message(message.chat.id, "نشد لیدربورد رو بیارم، بعداً دوباره امتحان کن 😿")


# ---------- هندل کردن 'mew' ----------

@dp.message_handler(lambda m: m.text and m.text.strip().lower() == "mew")
async def handle_mew(message: types.Message):
    try:
        # فقط توی گروه‌ها کار کنه
        if message.chat.type == "private":
            await bot.send_message(
                message.chat.id,
                "میو زدن فقط توی گروها فعاله 😼\nمنو به یه گروه اضافه کن.",
            )
            return

        tg_id = message.from_user.id
        username = message.from_user.username
        now_ts = int(time.time())

        u = get_user(tg_id)
        if not u:
            internal_id = get_or_create_user(tg_id, username)
            u = get_user(tg_id)
        else:
            internal_id = u["id"]

        # ثبت یوزر توی این گروه
        register_user_group(internal_id, message.chat.id)

        last_mew = u.get("last_mew_ts")
        if last_mew:
            diff = now_ts - int(last_mew)
            if diff < MEW_COOLDOWN:
                remain = MEW_COOLDOWN - diff
                mins = remain // 60
                secs = remain % 60
                await bot.send_message(
                    message.chat.id,
                    f"هنوز باید {mins} دقیقه و {secs} ثانیه صبر کنی تا دوباره میو بزنی 😼",
                    reply_to_message_id=message.message_id,
                )
                return

        gained = random.randint(3, 8)
        current_points = u.get("mew_points", 0)
        new_points = current_points + gained

        update_user_mew(tg_id, mew_points=new_points, last_mew_ts=now_ts)

        await bot.send_message(
            message.chat.id,
            f"میوووو 😸\n"
            f"+{gained} میو پوینت گرفتی! مجموع: <b>{new_points}</b>",
            reply_to_message_id=message.message_id,
        )
    except Exception as e:
        logger.exception("Error in handle_mew: %s", e)
        await notify_owner(f"❌ Error in handle_mew: {repr(e)}")
        await bot.send_message(
            message.chat.id,
            "یه مشکلی پیش اومد موقع شمردن میو 😿",
            reply_to_message_id=message.message_id,
        )


# ---------- گربه‌ها ----------

@dp.message_handler(commands=["mycats"])
async def cmd_mycats(message: types.Message):
    try:
        u = get_user(message.from_user.id)
        if not u:
            await bot.send_message(message.chat.id, "هنوز ثبت‌نام نکردی! اول /start رو بزن.")
            return

        cats = get_user_cats(u["id"])
        if not cats:
            await bot.send_message(message.chat.id, "هنوز هیچ گربه‌ای نداری 😿\nبا /newcat یکی بگیر!")
            return

        now_ts = int(time.time())
        lines = ["🐾 گربه‌های تو:"]
        for c in cats:
            c = _tick_cat_stats(c, now_ts)
            lines.append(
                f"ID: <code>{c['id']}</code> | 🐱 <b>{c['name']}</b> | "
                f"Lv {c['level']} | 🍗 {c['hunger']}/100 | 🎮 {c['happiness']}/100"
            )
        await bot.send_message(message.chat.id, "\n".join(lines))
    except Exception as e:
        logger.exception("Error in /mycats: %s", e)
        await notify_owner(f"❌ Error in /mycats: {repr(e)}")
        await bot.send_message(message.chat.id, "نتونستم گربه‌هات رو بیارم 😿")


@dp.message_handler(commands=["newcat"])
async def cmd_newcat(message: types.Message):
    """
    خرید گربه جدید: مثلا 50 میو پوینت هزینه.
    """
    try:
        COST = 50

        u = get_user(message.from_user.id)
        if not u:
            await bot.send_message(message.chat.id, "اول /start رو بزن تا ثبت‌نام شی 😺")
            return

        points = u.get("mew_points", 0)
        if points < COST:
            await bot.send_message(
                message.chat.id,
                f"برای گربه جدید حداقل {COST} میو پوینت لازم داری 😿\n"
                f"الان فقط {points} داری.",
            )
            return

        # ساخت گربه رندوم ساده
        names = ["Mimo", "Luna", "Shadow", "Neko", "Pumpkin", "Mizu", "Kuro"]
        rarities = ["Common", "Rare", "Epic", "Legendary"]
        elements = ["Fire", "Water", "Earth", "Air", "Void"]
        traits = ["Lazy", "Hyper", "Cuddly", "Grumpy", "Smart"]

        name = random.choice(names)
        rarity = random.choices(rarities, weights=[60, 25, 10, 5])[0]
        element = random.choice(elements)
        trait = random.choice(traits)
        desc = "یک گربه مرموز از سرزمین میولند 😼"

        cat_id = add_cat(
            owner_id=u["id"],
            name=name,
            rarity=rarity,
            element=element,
            trait=trait,
            description=desc,
        )

        # کم کردن پوینت
        update_user_mew(message.from_user.id, mew_points=points - COST)

        await bot.send_message(
            message.chat.id,
            f"🎉 یک گربه جدید گرفتی!\n\n"
            f"{_format_cat({'name': name, 'rarity': rarity, 'element': element, 'trait': trait, "
            f"'description': desc, 'level': 1, 'xp': 0, 'hunger': 60, 'happiness': 60})}\n\n"
            f"ID این گربه: <code>{cat_id}</code>",
        )
    except Exception as e:
        logger.exception("Error in /newcat: %s", e)
        await notify_owner(f"❌ Error in /newcat: {repr(e)}")
        await bot.send_message(message.chat.id, "گربه جدید ساختن خراب شد 😿")


@dp.message_handler(commands=["feed"])
async def cmd_feed(message: types.Message):
    """
    /feed <cat_id>
    """
    try:
        u = get_user(message.from_user.id)
        if not u:
            await bot.send_message(message.chat.id, "اول /start رو بزن 😺")
            return

        args = message.get_args().strip()
        if not args.isdigit():
            await bot.send_message(message.chat.id, "فرمت درست: /feed <cat_id>")
            return

        cat_id = int(args)
        cats = get_user_cats(u["id"])
        target = next((c for c in cats if c["id"] == cat_id), None)
        if not target:
            await bot.send_message(message.chat.id, "همچین گربه‌ای برای تو پیدا نشد 😿")
            return

        now_ts = int(time.time())
        target = _tick_cat_stats(target, now_ts)

        target["hunger"] = min(100, target["hunger"] + 20)
        target["happiness"] = min(100, target["happiness"] + 5)
        target["xp"] += 5

        # لول‌آپ ساده: هر 100 xp یک لول
        level = target["level"]
        while target["xp"] >= level * 100:
            target["xp"] -= level * 100
            level += 1
        target["level"] = level

        update_cat_stats(
            cat_id=target["id"],
            owner_id=u["id"],
            hunger=target["hunger"],
            happiness=target["happiness"],
            xp=target["xp"],
            level=target["level"],
            last_tick_ts=now_ts,
        )

        await bot.send_message(
            message.chat.id,
            f"🍗 به {target['name']} غذا دادی!\n\n{_format_cat(target)}",
        )

    except Exception as e:
        logger.exception("Error in /feed: %s", e)
        await notify_owner(f"❌ Error in /feed: {repr(e)}")
        await bot.send_message(message.chat.id, "نتونستم گربه رو غذا بدم 😿")


@dp.message_handler(commands=["play"])
async def cmd_play(message: types.Message):
    """
    /play <cat_id>
    """
    try:
        u = get_user(message.from_user.id)
        if not u:
            await bot.send_message(message.chat.id, "اول /start رو بزن 😺")
            return

        args = message.get_args().strip()
        if not args.isdigit():
            await bot.send_message(message.chat.id, "فرمت درست: /play <cat_id>")
            return

        cat_id = int(args)
        cats = get_user_cats(u["id"])
        target = next((c for c in cats if c["id"] == cat_id), None)
        if not target:
            await bot.send_message(message.chat.id, "همچین گربه‌ای برای تو نیست 😿")
            return

        now_ts = int(time.time())
        target = _tick_cat_stats(target, now_ts)

        target["happiness"] = min(100, target["happiness"] + 20)
        target["hunger"] = max(0, target["hunger"] - 5)
        target["xp"] += 5

        level = target["level"]
        while target["xp"] >= level * 100:
            target["xp"] -= level * 100
            level += 1
        target["level"] = level

        update_cat_stats(
            cat_id=target["id"],
            owner_id=u["id"],
            hunger=target["hunger"],
            happiness=target["happiness"],
            xp=target["xp"],
            level=target["level"],
            last_tick_ts=now_ts,
        )

        await bot.send_message(
            message.chat.id,
            f"🎮 با {target['name']} بازی کردی!\n\n{_format_cat(target)}",
        )

    except Exception as e:
        logger.exception("Error in /play: %s", e)
        await notify_owner(f"❌ Error in /play: {repr(e)}")
        await bot.send_message(message.chat.id, "نتونستم با گربه بازی کنم 😿")


@dp.message_handler(commands=["rename"])
async def cmd_rename(message: types.Message):
    """
    /rename <cat_id> <new_name>
    """
    try:
        u = get_user(message.from_user.id)
        if not u:
            await bot.send_message(message.chat.id, "اول /start رو بزن 😺")
            return

        args = message.get_args().strip().split(maxsplit=1)
        if len(args) != 2 or not args[0].isdigit():
            await bot.send_message(message.chat.id, "فرمت درست: /rename <cat_id> <اسم جدید>")
            return

        cat_id = int(args[0])
        new_name = args[1][:50]

        cats = get_user_cats(u["id"])
        target = next((c for c in cats if c["id"] == cat_id), None)
        if not target:
            await bot.send_message(message.chat.id, "همچین گربه‌ای برای تو نیست 😿")
            return

        rename_cat(u["id"], cat_id, new_name)
        await bot.send_message(
            message.chat.id,
            f"🐱 اسم گربه‌ات به <b>{new_name}</b> تغییر کرد!",
        )
    except Exception as e:
        logger.exception("Error in /rename: %s", e)
        await notify_owner(f"❌ Error in /rename: {repr(e)}")
        await bot.send_message(message.chat.id, "نشد اسم گربه رو عوض کنم 😿")


@dp.message_handler(commands=["transfer"])
async def cmd_transfer(message: types.Message):
    """
    /transfer <cat_id> <@username_or_id>
    """
    try:
        u = get_user(message.from_user.id)
        if not u:
            await bot.send_message(message.chat.id, "اول /start رو بزن 😺")
            return

        args = message.get_args().strip().split(maxsplit=2)
        if len(args) < 2 or not args[0].isdigit():
            await bot.send_message(
                message.chat.id,
                "فرمت درست: /transfer <cat_id> <@username یا user_id>",
            )
            return

        cat_id = int(args[0])
        target_user_raw = args[1]

        cats = get_user_cats(u["id"])
        target_cat = next((c for c in cats if c["id"] == cat_id), None)
        if not target_cat:
            await bot.send_message(message.chat.id, "همچین گربه‌ای برای تو نیست 😿")
            return

        # الان ساده: فقط با user_id کار کنیم
        if target_user_raw.startswith("@"):
            await bot.send_message(
                message.chat.id,
                "فعلاً فقط می‌تونی با user_id ترنسفر کنی (مثلاً /transfer 3 123456789).",
            )
            return

        if not target_user_raw.isdigit():
            await bot.send_message(
                message.chat.id,
                "user_id باید عدد باشه.",
            )
            return

        target_tg_id = int(target_user_raw)
        target_db_user = get_user(target_tg_id)
        if not target_db_user:
            await bot.send_message(
                message.chat.id,
                "اون کاربر هنوز /start رو نزده که ثبت بشه 😿",
            )
            return

        set_cat_owner(cat_id, target_db_user["id"])

        await bot.send_message(
            message.chat.id,
            f"🎁 گربه با ID <code>{cat_id}</code> به یوزر با آیدی <code>{target_tg_id}</code> منتقل شد.",
        )

    except Exception as e:
        logger.exception("Error in /transfer: %s", e)
        await notify_owner(f"❌ Error in /transfer: {repr(e)}")
        await bot.send_message(message.chat.id, "نشد گربه رو ترنسفر کنم 😿")


# ---------- root و webhook ----------

async def index(request: web.Request):
    return web.Response(text="Mewland bot is running 😺")


async def handle_webhook(request: web.Request):
    # چک کن توکن توی URL همونی باشه که ما ثبت کردیم
    token_in_path = request.match_info.get("token")
    if token_in_path != BOT_TOKEN:
        return web.Response(status=403, text="Forbidden")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Bad request")

    update = types.Update(**data)
    await dp.process_update(update)
    return web.Response(text="OK")


async def on_startup(app: web.Application):
    logger.info("Setting webhook to %s", WEBHOOK_URL)
    try:
        # مطمئن شو وبهوک قبلی پاک بشه
        await bot.delete_webhook()
        await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message"])
        await notify_owner("🚀 Mewland bot started روی Render.")
    except TelegramAPIError as e:
        logger.exception("Error setting webhook: %s", e)
        await notify_owner(f"❌ Error setting webhook: {repr(e)}")


async def on_shutdown(app: web.Application):
    logger.info("Shutting down, deleting webhook...")
    try:
        await bot.delete_webhook()
    except Exception as e:
        logger.error("Error deleting webhook on shutdown: %s", e)


def main():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/webhook/{token}", handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, host=APP_HOST, port=APP_PORT)


if __name__ == "__main__":
    main()
