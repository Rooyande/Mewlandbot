import asyncio
import logging
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    BOT_TOKEN,
    REQUIRED_GROUP_CHAT_ID,
    REQUIRED_GROUP_INVITE_LINK,
    OWNER_ID,
)
from db import init_db, open_db
from ui import home_keyboard, back_home_keyboard, render_home_text
from economy import meow_try
from passive import apply_passive
from cats import open_standard_box, open_premium_box
from cats_ui import (
    fetch_user_cats_page,
    cats_list_keyboard,
    render_user_cats_page_text,
    render_cat_details,
    cat_details_keyboard,
    fetch_cat_media,
)
from feedplay import apply_survival, feed_all, play_all
from admin import (
    admin_menu_keyboard,
    admin_menu_text,
    admin_addcat_start,
    admin_addcat_handle_message,
    admin_addcat_confirm,
    admin_addcat_cancel,
)

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


async def _touch_economy(user_id: int) -> None:
    await apply_passive(user_id)
    await apply_survival(user_id)


async def _edit_or_reply(update: Update, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if update.callback_query and update.callback_query.message:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
        except TelegramError:
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
        return
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def _send_media(context: ContextTypes.DEFAULT_TYPE, chat_id: int, media: dict) -> None:
    mt = media.get("media_type")
    fid = media.get("media_file_id")
    if not mt or not fid:
        return
    if mt == "photo":
        await context.bot.send_photo(chat_id=chat_id, photo=fid)
    elif mt == "video":
        await context.bot.send_video(chat_id=chat_id, video=fid)


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return

    await _ensure_user(user_id)
    await _touch_economy(user_id)

    text = await render_home_text(user_id)
    await _edit_or_reply(update, text, home_keyboard(user_id))


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


def _shop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Standard Box", callback_data="shop:std")],
            [InlineKeyboardButton("Premium Box", callback_data="shop:prem")],
            [InlineKeyboardButton("Back", callback_data="nav:home")],
        ]
    )


async def shop_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _edit_or_reply(update, "Shop", _shop_keyboard())


async def shop_std(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)
    await _touch_economy(user_id)

    res = await open_standard_box(user_id)
    if not res.ok:
        msg = "Shop error."
        if res.reason == "no_mp":
            msg = "MP کافی نیست."
        elif res.reason == "empty_pool":
            msg = "کاتالوگ برای Standard خالی است."
        await _edit_or_reply(update, msg, _shop_keyboard())
        return

    if update.effective_chat:
        if res.outcome and "user_cat_id" in res.outcome:
            media = await fetch_cat_media(user_id, int(res.outcome["user_cat_id"]))
            if media:
                await _send_media(context, update.effective_chat.id, media)
        else:
            # fallback: send catalog media
            if res.cat and res.cat.media_type and res.cat.media_file_id:
                await _send_media(
                    context,
                    update.effective_chat.id,
                    {"media_type": res.cat.media_type, "media_file_id": res.cat.media_file_id},
                )

    cat = res.cat
    out = res.outcome or {}
    text = f"Standard Box نتیجه:\n\n{cat.name} ({cat.rarity})"
    if out.get("type") == "new":
        text += "\nNew cat!"
    elif out.get("type") in ("dup", "dup_max"):
        if out.get("level_up"):
            text += f"\nDuplicate → Level Up! (Lvl {out.get('level')})"
        else:
            text += f"\nDuplicate. (Lvl {out.get('level')})"

    await _edit_or_reply(update, text, _shop_keyboard())


async def shop_prem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)
    await _touch_economy(user_id)

    res = await open_premium_box(user_id)
    if not res.ok:
        msg = "Shop error."
        if res.reason == "no_mp":
            msg = "MP کافی نیست."
        elif res.reason == "empty_pool":
            msg = "کاتالوگ برای Premium خالی است."
        await _edit_or_reply(update, msg, _shop_keyboard())
        return

    if update.effective_chat:
        if res.outcome and "user_cat_id" in res.outcome:
            media = await fetch_cat_media(user_id, int(res.outcome["user_cat_id"]))
            if media:
                await _send_media(context, update.effective_chat.id, media)
        else:
            if res.cat and res.cat.media_type and res.cat.media_file_id:
                await _send_media(
                    context,
                    update.effective_chat.id,
                    {"media_type": res.cat.media_type, "media_file_id": res.cat.media_file_id},
                )

    cat = res.cat
    out = res.outcome or {}
    text = f"Premium Box نتیجه:\n\n{cat.name} ({cat.rarity})"
    if out.get("type") == "new":
        text += "\nNew cat!"
    elif out.get("type") in ("dup", "dup_max"):
        if out.get("level_up"):
            text += f"\nDuplicate → Level Up! (Lvl {out.get('level')})"
        else:
            text += f"\nDuplicate. (Lvl {out.get('level')})"

    await _edit_or_reply(update, text, _shop_keyboard())


async def meow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_join_gate(update, context):
        return

    user_id = _user_id_from_update(update)
    if user_id is None:
        return

    await _ensure_user(user_id)
    await _touch_economy(user_id)

    res = await meow_try(user_id)
    if not res.ok:
        if update.message:
            if res.reason == "cooldown":
                await update.message.reply_text(f"Cooldown: {res.wait_sec}s")
            else:
                await update.message.reply_text("Daily limit reached.")
        return

    await show_home(update, context)


async def meow_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

    if not await _check_join_gate(update, context):
        return

    user_id = _user_id_from_update(update)
    if user_id is None:
        return

    await _ensure_user(user_id)
    await _touch_economy(user_id)

    res = await meow_try(user_id)
    if not res.ok:
        q = update.callback_query
        if q and q.message:
            if res.reason == "cooldown":
                await q.message.edit_text(f"Cooldown: {res.wait_sec}s", reply_markup=home_keyboard(user_id))
            else:
                await q.message.edit_text("Daily limit reached.", reply_markup=home_keyboard(user_id))
        return

    await show_home(update, context)


async def my_cats_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)
    await _touch_economy(user_id)

    rows, has_prev, has_next = await fetch_user_cats_page(user_id, page)
    text = await render_user_cats_page_text(user_id, page)
    kb = cats_list_keyboard(rows, page, has_prev, has_next)
    await _edit_or_reply(update, text, kb)


async def my_cat_open(update: Update, context: ContextTypes.DEFAULT_TYPE, user_cat_id: int) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)
    await _touch_economy(user_id)

    if update.effective_chat:
        media = await fetch_cat_media(user_id, user_cat_id)
        if media:
            await _send_media(context, update.effective_chat.id, media)

    text = await render_cat_details(user_id, user_cat_id)
    kb = cat_details_keyboard(user_cat_id)
    await _edit_or_reply(update, text, kb)


async def my_cat_feed(update: Update, context: ContextTypes.DEFAULT_TYPE, user_cat_id: int) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)
    await _touch_economy(user_id)

    now = int(time.time())
    db = await open_db()
    try:
        await db.execute(
            "UPDATE user_cats SET last_feed_at=? WHERE user_id=? AND id=? AND status='active'",
            (now, user_id, user_cat_id),
        )
        await db.commit()
    finally:
        await db.close()

    await my_cat_open(update, context, user_cat_id)


async def my_cat_play(update: Update, context: ContextTypes.DEFAULT_TYPE, user_cat_id: int) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)
    await _touch_economy(user_id)

    now = int(time.time())
    db = await open_db()
    try:
        await db.execute(
            "UPDATE user_cats SET last_play_at=? WHERE user_id=? AND id=? AND status='active'",
            (now, user_id, user_cat_id),
        )
        await db.commit()
    finally:
        await db.close()

    await my_cat_open(update, context, user_cat_id)


async def cats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

    if not await _check_join_gate(update, context):
        return

    data = update.callback_query.data if update.callback_query else ""
    parts = data.split(":")

    if data.startswith("cat:list:") and len(parts) == 3:
        try:
            page = int(parts[2])
        except Exception:
            page = 0
        await my_cats_list(update, context, page)
        return

    if data.startswith("cat:open:") and len(parts) == 3:
        try:
            uc_id = int(parts[2])
        except Exception:
            return
        await my_cat_open(update, context, uc_id)
        return

    if data.startswith("cat:feed:") and len(parts) == 3:
        try:
            uc_id = int(parts[2])
        except Exception:
            return
        await my_cat_feed(update, context, uc_id)
        return

    if data.startswith("cat:play:") and len(parts) == 3:
        try:
            uc_id = int(parts[2])
        except Exception:
            return
        await my_cat_play(update, context, uc_id)
        return

    await my_cats_list(update, context, 0)


async def feed_all_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()
    if not await _check_join_gate(update, context):
        return
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)
    await _touch_economy(user_id)
    await feed_all(user_id)
    await show_home(update, context)


async def play_all_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()
    if not await _check_join_gate(update, context):
        return
    user_id = _user_id_from_update(update)
    if user_id is None:
        return
    await _ensure_user(user_id)
    await _touch_economy(user_id)
    await play_all(user_id)
    await show_home(update, context)


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_join_gate(update, context):
        return
    user_id = _user_id_from_update(update)
    if user_id != OWNER_ID:
        return
    await _edit_or_reply(update, await admin_menu_text(), admin_menu_keyboard())


async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

    if not await _check_join_gate(update, context):
        return

    user_id = _user_id_from_update(update)
    if user_id != OWNER_ID:
        return

    data = update.callback_query.data if update.callback_query else ""

    if data == "admin:addcat":
        txt = await admin_addcat_start(user_id, context)
        await _edit_or_reply(update, txt)
        return

    if data == "admin:addcat:confirm":
        txt = await admin_addcat_confirm(user_id, context)
        await _edit_or_reply(update, txt, admin_menu_keyboard())
        return

    if data == "admin:addcat:cancel":
        txt = await admin_addcat_cancel(context)
        await _edit_or_reply(update, txt, admin_menu_keyboard())
        return

    await _edit_or_reply(update, await admin_menu_text(), admin_menu_keyboard())


async def admin_msg_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _user_id_from_update(update)
    if user_id is None:
        return

    if update.effective_chat and update.effective_chat.type != "private":
        return
    if user_id != OWNER_ID:
        return

    out = await admin_addcat_handle_message(user_id, update, context)
    if out and update.message:
        await update.message.reply_text(out)


async def nav_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

    if not await _check_join_gate(update, context):
        return

    user_id = _user_id_from_update(update)
    if user_id is None:
        return

    await _ensure_user(user_id)
    await _touch_economy(user_id)

    q = update.callback_query
    data = "" if q is None else (q.data or "")

    if data == "nav:home":
        await show_home(update, context)
        return

    if data == "nav:shop":
        await shop_view(update, context)
        return

    if data == "nav:cats":
        await my_cats_list(update, context, 0)
        return

    if data == "nav:feedall":
        await feed_all_cb(update, context)
        return

    if data == "nav:playall":
        await play_all_cb(update, context)
        return

    if data == "nav:admin":
        if user_id == OWNER_ID:
            await _edit_or_reply(update, await admin_menu_text(), admin_menu_keyboard())
        return

    await _edit_or_reply(update, "در حال توسعه.", back_home_keyboard())


async def shop_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()

    if not await _check_join_gate(update, context):
        return

    data = update.callback_query.data if update.callback_query else ""
    if data == "shop:std":
        await shop_std(update, context)
    elif data == "shop:prem":
        await shop_prem(update, context)
    else:
        await shop_view(update, context)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing")

    asyncio.run(init_db())

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("meow", meow_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))

    app.add_handler(MessageHandler(filters.ALL, admin_msg_router))

    app.add_handler(CallbackQueryHandler(verify_cb, pattern=r"^verify$"))
    app.add_handler(CallbackQueryHandler(meow_cb, pattern=r"^act:meow$"))

    app.add_handler(CallbackQueryHandler(shop_cb, pattern=r"^shop:"))
    app.add_handler(CallbackQueryHandler(cats_cb, pattern=r"^cat:"))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(nav_cb, pattern=r"^nav:"))

    app.add_handler(CallbackQueryHandler(nav_cb))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
