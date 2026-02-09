import asyncio
import logging
import time

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import (
    BOT_TOKEN,
    REQUIRED_GROUP_CHAT_ID,
    REQUIRED_GROUP_INVITE_LINK,
)
from db import init_db, open_db
from ui import home_keyboard, back_home_keyboard, render_home_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("meowland")


def _user_id_from_update(update: Update) -> int | None:
    if update.effective_user:
        return update.effective_user.id
    return None


def _join_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    if REQUIRED_GROUP_INVITE_LINK:
        buttons.append([InlineKeyboardButton("Join", url=REQUIRED_GROUP_INVITE_LINK)])
    buttons.append([InlineKeyboardButton("Verify", callback_data="verify")])
    return InlineKeyboardMarkup(buttons)


async def _send_or_edit_join_gate(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if update.callback_query and update.callback_query.message:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=_join_keyboard())
        except TelegramError:
            await update.callback_query.message.reply_text(text, reply_markup=_join_keyboard())
        return
    if update.message:
        await update.message.reply_text(text, reply_markup=_join_keyboard())


async def _check_join_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return False

    if REQUIRED_GROUP_CHAT_ID == 0:
        await _send_or_edit_join_gate(update, context, "بات هنوز پیکربندی نشده است.")
        return False

    try:
        member = await context.bot.get_chat_member(REQUIRED_GROUP_CHAT_ID, user_id)
        status = getattr(member, "status", None)
        ok = status in ("member", "administrator", "creator")
        if not ok:
            await _send_or_edit_join_gate(update, context, "برای استفاده باید عضو گروه باشید.")
        return ok
    except TelegramError as e:
        log.warning("get_chat_member failed: %s", e)
        await _send_or_edit_join_gate(update, context, "بررسی عضویت ممکن نیست. با ادمین تماس بگیرید.")
        return False


async def _ensure_user(user_id: int) -> None:
    now = int(time.time())
    db = await open_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id, mp_balance, last_passive_ts, shelter_level, created_at) "
            "VALUES(?, 0, ?, 1, ?)",
            (user_id, now, now),
        )
        await db.execute(
            "INSERT OR IGNORE INTO resources(user_id, essence) VALUES(?, 0)",
            (user_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)

    text = await render_home_text(user_id)

    if update.callback_query and update.callback_query.message:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=home_keyboard())
        except TelegramError:
            await update.callback_query.message.reply_text(text, reply_markup=home_keyboard())
        return

    if update.message:
        await update.message.reply_text(text, reply_markup=home_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_join_gate(update, context):
        return
    await show_home(update, context)


async def verify_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

    if not await _check_join_gate(update, context):
        return

    await show_home(update, context)


async def nav_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

    if not await _check_join_gate(update, context):
        return

    q = update.callback_query
    data = "" if q is None else (q.data or "")
    if data == "nav:home":
        await show_home(update, context)
        return

    if q and q.message:
        await _ensure_user(_user_id_from_update(update) or 0)
        await q.message.edit_text("در حال توسعه.", reply_markup=back_home_keyboard())


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing")

    asyncio.run(init_db())

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_cb, pattern=r"^verify$"))
    app.add_handler(CallbackQueryHandler(nav_cb, pattern=r"^nav:"))
    app.add_handler(CallbackQueryHandler(nav_cb))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
