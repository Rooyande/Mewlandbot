import json
import time
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import OWNER_ID
from db import open_db


RARITIES = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine"]
MEDIA_TYPES = ["photo", "video"]


def _now() -> int:
    return int(time.time())


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def _admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Add Cat", callback_data="admin:addcat")],
            [InlineKeyboardButton("Back", callback_data="nav:home")],
        ]
    )


async def admin_menu_text() -> str:
    return "Admin Panel"


async def admin_addcat_start(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data["admin_addcat"] = {
        "step": "name",
        "data": {},
    }
    return "Add Cat\n\nStep 1/6: ارسال نام گربه (text)."


async def admin_addcat_cancel(context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data.pop("admin_addcat", None)
    return "لغو شد."


async def admin_addcat_handle_message(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    st = context.user_data.get("admin_addcat")
    if not st:
        return None
    if not _is_owner(user_id):
        return "دسترسی ندارید."

    step = st.get("step")
    data = st.get("data", {})
    msg = update.message

    if step == "name":
        if not msg or not msg.text:
            return "نام باید text باشد."
        data["name"] = msg.text.strip()
        st["step"] = "description"
        return "Step 2/6: توضیحات (text)."

    if step == "description":
        if not msg or not msg.text:
            return "توضیح باید text باشد."
        data["description"] = msg.text.strip()
        st["step"] = "rarity"
        return "Step 3/6: rarity را دقیقاً یکی از این‌ها بفرست:\nCommon / Uncommon / Rare / Epic / Legendary / Mythic / Divine"

    if step == "rarity":
        if not msg or not msg.text:
            return "rarity باید text باشد."
        r = msg.text.strip()
        if r not in RARITIES:
            return "مقدار rarity نامعتبر است."
        data["rarity"] = r
        st["step"] = "base_rate"
        return "Step 4/6: base_passive_rate (عدد MP/hour). مثال: 1.5"

    if step == "base_rate":
        if not msg or not msg.text:
            return "عدد لازم است."
        try:
            v = float(msg.text.strip())
        except Exception:
            return "عدد نامعتبر است."
        data["base_passive_rate"] = v
        st["step"] = "media"
        return "Step 5/6: یک photo یا video ارسال کن (فایل تلگرام)."

    if step == "media":
        if not msg:
            return "media لازم است."
        if msg.photo:
            data["media_type"] = "photo"
            data["media_file_id"] = msg.photo[-1].file_id
        elif msg.video:
            data["media_type"] = "video"
            data["media_file_id"] = msg.video.file_id
        else:
            return "فقط photo یا video."
        st["step"] = "pools"
        return "Step 6/6: pools_enabled را به شکل CSV بفرست. مثال:\nStandard,Premium,Shop"

    if step == "pools":
        if not msg or not msg.text:
            return "CSV لازم است."
        pools = [p.strip() for p in msg.text.split(",") if p.strip()]
        data["pools_enabled"] = ",".join(pools) if pools else "Standard"
        st["step"] = "confirm"
        st["data"] = data
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Confirm", callback_data="admin:addcat:confirm")],
                [InlineKeyboardButton("Cancel", callback_data="admin:addcat:cancel")],
            ]
        )
        preview = (
            "Preview\n\n"
            f"Name: {data['name']}\n"
            f"Rarity: {data['rarity']}\n"
            f"Base: {data['base_passive_rate']} MP/h\n"
            f"Pools: {data['pools_enabled']}\n\n"
            f"{data['description']}"
        )
        await update.message.reply_text(preview, reply_markup=kb)
        return "Preview ارسال شد."

    return None


async def admin_addcat_confirm(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    st = context.user_data.get("admin_addcat")
    if not st or st.get("step") != "confirm":
        return "چیزی برای تایید نیست."
    if not _is_owner(user_id):
        return "دسترسی ندارید."

    data = st.get("data", {})
    now = _now()

    db = await open_db()
    try:
        await db.execute(
            """
            INSERT INTO cats_catalog(
              name, description, rarity, base_passive_rate,
              media_type, media_file_id, active, pools_enabled,
              available_from, available_until, tags, created_at
            ) VALUES(?,?,?,?,?, ?, 1, ?, NULL, NULL, NULL, ?)
            """,
            (
                data["name"],
                data["description"],
                data["rarity"],
                float(data["base_passive_rate"]),
                data["media_type"],
                data["media_file_id"],
                data["pools_enabled"],
                now,
            ),
        )
        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,?)",
            (user_id, "add_cat", json.dumps(data, ensure_ascii=False), now),
        )
        await db.commit()
    finally:
        await db.close()

    context.user_data.pop("admin_addcat", None)
    return "ثبت شد."


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return _admin_menu_kb()
