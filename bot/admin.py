# bot/admin.py
import json
import time
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import OWNER_ID
from db import open_db, set_config, get_config

RARITIES = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine"]
MEDIA_TYPES = ["photo", "video"]

DUP_THRESHOLDS = {
    "Common": 25,
    "Uncommon": 15,
    "Rare": 8,
    "Epic": 4,
    "Legendary": 2,
    "Mythic": 1,
    "Divine": 10**9,
}


def _now() -> int:
    return int(time.time())


def _is_owner(user_id: int) -> bool:
    return int(user_id) == int(OWNER_ID)


async def is_admin(user_id: int) -> bool:
    if _is_owner(user_id):
        return True
    db = await open_db()
    try:
        cur = await db.execute("SELECT role FROM admin_roles WHERE user_id=?", (int(user_id),))
        r = await cur.fetchone()
        return r is not None
    finally:
        await db.close()


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Add Cat", callback_data="admin:addcat")],
            [InlineKeyboardButton("Add Item", callback_data="admin:additem")],
            [InlineKeyboardButton("Item Shop Admin", callback_data="admin:ishop")],
            [InlineKeyboardButton("Set Required Group", callback_data="admin:setgroup")],
            [InlineKeyboardButton("Set Config (Key/Value)", callback_data="admin:setcfg")],
            [InlineKeyboardButton("Grant/Take", callback_data="admin:grant")],
            [InlineKeyboardButton("Ban/Unban", callback_data="admin:ban")],
            [InlineKeyboardButton("View Logs", callback_data="admin:logs:0")],
            [InlineKeyboardButton("Back", callback_data="nav:home")],
        ]
    )


async def admin_menu_text() -> str:
    return "Admin Panel"


# ----------------------------
# Add Cat (Wizard)
# ----------------------------
async def admin_addcat_start(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data["admin_addcat"] = {"step": "name", "data": {}}
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
            (int(user_id), "add_cat", json.dumps(data, ensure_ascii=False), int(now)),
        )
        await db.commit()
    finally:
        await db.close()

    context.user_data.pop("admin_addcat", None)
    return "ثبت شد."


# ----------------------------
# Set Required Group (Wizard)
# ----------------------------
async def admin_setgroup_start(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    if not _is_owner(user_id):
        return "دسترسی ندارید.", InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="nav:admin")]])
    context.user_data["admin_setgroup"] = {"step": "chat_id", "data": {}}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:setgroup:cancel")]])
    return "Set Required Group\n\nStep 1/2: chat_id گروه/سوپرگروه را بفرست (عدد).", kb


async def admin_setgroup_cancel(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    context.user_data.pop("admin_setgroup", None)
    return "لغو شد.", admin_menu_keyboard()


async def admin_setgroup_handle_message(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[tuple[str, InlineKeyboardMarkup]]:
    st = context.user_data.get("admin_setgroup")
    if not st:
        return None
    if not _is_owner(user_id):
        return ("دسترسی ندارید.", admin_menu_keyboard())

    msg = update.message
    if not msg or not msg.text:
        return ("متن لازم است.", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:setgroup:cancel")]]))

    step = st.get("step")
    data = st.get("data", {})

    if step == "chat_id":
        try:
            chat_id = int(msg.text.strip())
        except Exception:
            return ("chat_id نامعتبر است.", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:setgroup:cancel")]]))
        data["required_group_chat_id"] = chat_id
        st["step"] = "invite"
        st["data"] = data
        return ("Step 2/2: لینک دعوت/عمومی را بفرست (یا - برای خالی).", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:setgroup:cancel")]]))

    if step == "invite":
        link = msg.text.strip()
        if link == "-":
            link = ""
        data["required_group_invite_link"] = link
        st["step"] = "confirm"
        st["data"] = data
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Confirm", callback_data="admin:setgroup:confirm")],
                [InlineKeyboardButton("Cancel", callback_data="admin:setgroup:cancel")],
            ]
        )
        preview = (
            "Preview\n\n"
            f"required_group_chat_id: {data['required_group_chat_id']}\n"
            f"required_group_invite_link: {data['required_group_invite_link'] or '-'}"
        )
        await msg.reply_text(preview, reply_markup=kb)
        return ("Preview ارسال شد.", kb)

    return None


async def admin_setgroup_confirm(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    st = context.user_data.get("admin_setgroup")
    if not st or st.get("step") != "confirm":
        return "چیزی برای تایید نیست.", admin_menu_keyboard()
    if not _is_owner(user_id):
        return "دسترسی ندارید.", admin_menu_keyboard()

    data = st.get("data", {})
    await set_config("required_group_chat_id", str(int(data["required_group_chat_id"])))
    await set_config("required_group_invite_link", str(data.get("required_group_invite_link", "")))

    now = _now()
    db = await open_db()
    try:
        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,?)",
            (int(user_id), "set_required_group", json.dumps(data, ensure_ascii=False), int(now)),
        )
        await db.commit()
    finally:
        await db.close()

    context.user_data.pop("admin_setgroup", None)
    return "ثبت شد.", admin_menu_keyboard()


# ----------------------------
# Set Config (Key/Value Wizard)
# ----------------------------
async def admin_setcfg_start(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    if not _is_owner(user_id):
        return "دسترسی ندارید.", admin_menu_keyboard()
    context.user_data["admin_setcfg"] = {"step": "key", "data": {}}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:setcfg:cancel")]])
    return "Set Config\n\nStep 1/2: key را بفرست.", kb


async def admin_setcfg_cancel(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    context.user_data.pop("admin_setcfg", None)
    return "لغو شد.", admin_menu_keyboard()


async def admin_setcfg_handle_message(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[tuple[str, InlineKeyboardMarkup]]:
    st = context.user_data.get("admin_setcfg")
    if not st:
        return None
    if not _is_owner(user_id):
        return ("دسترسی ندارید.", admin_menu_keyboard())

    msg = update.message
    if not msg or not msg.text:
        return ("متن لازم است.", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:setcfg:cancel")]]))

    step = st.get("step")
    data = st.get("data", {})

    if step == "key":
        k = msg.text.strip()
        if not k or len(k) > 200:
            return ("key نامعتبر است.", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:setcfg:cancel")]]))
        data["key"] = k
        st["step"] = "value"
        st["data"] = data
        return ("Step 2/2: value را بفرست (متن/JSON).", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:setcfg:cancel")]]))

    if step == "value":
        v = msg.text.strip()
        data["value"] = v
        st["step"] = "confirm"
        st["data"] = data
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Confirm", callback_data="admin:setcfg:confirm")],
                [InlineKeyboardButton("Cancel", callback_data="admin:setcfg:cancel")],
            ]
        )
        await msg.reply_text(f"Preview\n\n{data['key']} = {data['value']}", reply_markup=kb)
        return ("Preview ارسال شد.", kb)

    return None


async def admin_setcfg_confirm(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    st = context.user_data.get("admin_setcfg")
    if not st or st.get("step") != "confirm":
        return "چیزی برای تایید نیست.", admin_menu_keyboard()
    if not _is_owner(user_id):
        return "دسترسی ندارید.", admin_menu_keyboard()

    data = st.get("data", {})
    await set_config(str(data["key"]), str(data["value"]))

    now = _now()
    db = await open_db()
    try:
        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,?)",
            (int(user_id), "set_config", json.dumps({"key": data["key"]}, ensure_ascii=False), int(now)),
        )
        await db.commit()
    finally:
        await db.close()

    context.user_data.pop("admin_setcfg", None)
    return "ثبت شد.", admin_menu_keyboard()


# ----------------------------
# Grant/Take (Wizard)
# ----------------------------
def admin_grant_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("MP", callback_data="admin:grant:mp")],
            [InlineKeyboardButton("Essence", callback_data="admin:grant:ess")],
            [InlineKeyboardButton("Item", callback_data="admin:grant:item")],
            [InlineKeyboardButton("Cat", callback_data="admin:grant:cat")],
            [InlineKeyboardButton("Cancel", callback_data="admin:grant:cancel")],
        ]
    )


async def admin_grant_start(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    if not _is_owner(user_id):
        return "دسترسی ندارید.", admin_menu_keyboard()
    context.user_data["admin_grant"] = {"step": "pick", "data": {}}
    return "Grant/Take\n\nنوع را انتخاب کن.", admin_grant_kb()


async def admin_grant_cancel(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    context.user_data.pop("admin_grant", None)
    return "لغو شد.", admin_menu_keyboard()


async def admin_grant_pick(kind: str, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    st = context.user_data.get("admin_grant") or {"data": {}}
    st["data"] = {"kind": kind}
    st["step"] = "user_id"
    context.user_data["admin_grant"] = st
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:grant:cancel")]])
    return "Step 1/3: user_id را بفرست (عدد).", kb


async def admin_grant_handle_message(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[tuple[str, InlineKeyboardMarkup]]:
    st = context.user_data.get("admin_grant")
    if not st:
        return None
    if not _is_owner(user_id):
        return ("دسترسی ندارید.", admin_menu_keyboard())

    msg = update.message
    if not msg or not msg.text:
        return ("متن لازم است.", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:grant:cancel")]]))

    step = st.get("step")
    data = st.get("data", {})
    kb_cancel = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:grant:cancel")]])

    if step == "user_id":
        try:
            tu = int(msg.text.strip())
        except Exception:
            return ("user_id نامعتبر است.", kb_cancel)
        data["target_user_id"] = tu
        st["data"] = data
        st["step"] = "arg1"
        kind = data.get("kind")
        if kind in ("mp", "ess"):
            return ("Step 2/3: amount را بفرست (می‌تواند منفی باشد).", kb_cancel)
        if kind == "item":
            return ("Step 2/3: item_id را بفرست (عدد).", kb_cancel)
        if kind == "cat":
            return ("Step 2/3: cat_id را بفرست (عدد).", kb_cancel)
        return ("نوع نامعتبر.", kb_cancel)

    if step == "arg1":
        kind = data.get("kind")
        if kind in ("mp", "ess"):
            try:
                amt = int(msg.text.strip())
            except Exception:
                return ("amount نامعتبر است.", kb_cancel)
            data["amount"] = amt
            st["step"] = "confirm"
        elif kind in ("item", "cat"):
            try:
                x = int(msg.text.strip())
            except Exception:
                return ("عدد نامعتبر است.", kb_cancel)
            data["arg1"] = x
            st["step"] = "arg2" if kind == "item" else "confirm"
        else:
            return ("نوع نامعتبر.", kb_cancel)

        st["data"] = data
        if st["step"] == "arg2":
            return ("Step 3/3: qty را بفرست (می‌تواند منفی باشد).", kb_cancel)

        preview = f"Preview\n\nkind: {kind}\nuser_id: {data['target_user_id']}\n"
        if kind in ("mp", "ess"):
            preview += f"amount: {data['amount']}"
        elif kind == "cat":
            preview += f"cat_id: {data['arg1']}"
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Confirm", callback_data="admin:grant:confirm")],
                [InlineKeyboardButton("Cancel", callback_data="admin:grant:cancel")],
            ]
        )
        await msg.reply_text(preview, reply_markup=kb)
        return ("Preview ارسال شد.", kb)

    if step == "arg2":
        kind = data.get("kind")
        if kind != "item":
            return ("نوع نامعتبر.", kb_cancel)
        try:
            qty = int(msg.text.strip())
        except Exception:
            return ("qty نامعتبر است.", kb_cancel)
        data["qty"] = qty
        st["data"] = data
        st["step"] = "confirm"

        preview = f"Preview\n\nkind: item\nuser_id: {data['target_user_id']}\nitem_id: {data['arg1']}\nqty: {data['qty']}"
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Confirm", callback_data="admin:grant:confirm")],
                [InlineKeyboardButton("Cancel", callback_data="admin:grant:cancel")],
            ]
        )
        await msg.reply_text(preview, reply_markup=kb)
        return ("Preview ارسال شد.", kb)

    return None


async def _grant_mp(db, target_user_id: int, amount: int) -> None:
    now = _now()
    await db.execute(
        "INSERT OR IGNORE INTO users(user_id, mp_balance, last_passive_ts, shelter_level, created_at) VALUES(?,0,?,?,?)",
        (int(target_user_id), int(now), 1, int(now)),
    )
    await db.execute("UPDATE users SET mp_balance = mp_balance + ? WHERE user_id=?", (int(amount), int(target_user_id)))


async def _grant_ess(db, target_user_id: int, amount: int) -> None:
    await db.execute("INSERT OR IGNORE INTO resources(user_id, essence) VALUES(?,0)", (int(target_user_id),))
    await db.execute("UPDATE resources SET essence = essence + ? WHERE user_id=?", (int(amount), int(target_user_id)))


async def _grant_item(db, target_user_id: int, item_id: int, qty: int) -> None:
    await db.execute("INSERT OR IGNORE INTO user_items(user_id, item_id, qty) VALUES(?,?,0)", (int(target_user_id), int(item_id)))
    await db.execute("UPDATE user_items SET qty = qty + ? WHERE user_id=? AND item_id=?", (int(qty), int(target_user_id), int(item_id)))
    # clamp to 0
    await db.execute("UPDATE user_items SET qty=0 WHERE user_id=? AND item_id=? AND qty < 0", (int(target_user_id), int(item_id)))


async def _grant_cat_dup_logic(db, target_user_id: int, cat_id: int) -> dict:
    now = _now()
    await db.execute(
        "INSERT OR IGNORE INTO users(user_id, mp_balance, last_passive_ts, shelter_level, created_at) VALUES(?,0,?,?,?)",
        (int(target_user_id), int(now), 1, int(now)),
    )
    await db.execute("INSERT OR IGNORE INTO resources(user_id, essence) VALUES(?,0)", (int(target_user_id),))

    cur = await db.execute("SELECT rarity FROM cats_catalog WHERE cat_id=?", (int(cat_id),))
    cr = await cur.fetchone()
    if cr is None:
        return {"ok": False, "reason": "cat_not_found"}
    rarity = str(cr["rarity"] or "Common")

    cur = await db.execute(
        "SELECT id, level, dup_counter FROM user_cats WHERE user_id=? AND cat_id=? ORDER BY id LIMIT 1",
        (int(target_user_id), int(cat_id)),
    )
    owned = await cur.fetchone()

    if owned is None:
        await db.execute(
            """
            INSERT INTO user_cats(user_id, cat_id, level, dup_counter, status, last_feed_at, last_play_at, obtained_at)
            VALUES(?, ?, 1, 0, 'active', ?, ?, ?)
            """,
            (int(target_user_id), int(cat_id), int(now), int(now), int(now)),
        )
        return {"ok": True, "type": "new"}

    # duplicate (basic)
    level = int(owned["level"] or 1)
    dup = int(owned["dup_counter"] or 0)

    max_level = 20
    try:
        cur2 = await db.execute("SELECT value FROM config WHERE key='max_level'")
        rr = await cur2.fetchone()
        if rr is not None:
            max_level = int(rr["value"])
    except Exception:
        max_level = 20

    if level >= max_level:
        return {"ok": True, "type": "dup_max", "level": level}

    dup += 1
    th = int(DUP_THRESHOLDS.get(rarity, 25))
    level_up = False
    if dup >= th:
        level += 1
        dup = 0
        level_up = True

    await db.execute("UPDATE user_cats SET level=?, dup_counter=? WHERE id=?", (int(level), int(dup), int(owned["id"])))
    return {"ok": True, "type": "dup", "level": level, "level_up": level_up}


async def admin_grant_confirm(admin_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    st = context.user_data.get("admin_grant")
    if not st or st.get("step") != "confirm":
        return "چیزی برای تایید نیست.", admin_menu_keyboard()
    if not _is_owner(admin_id):
        return "دسترسی ندارید.", admin_menu_keyboard()

    data = st.get("data", {})
    kind = data.get("kind")
    tu = int(data.get("target_user_id", 0))
    now = _now()

    db = await open_db()
    try:
        if kind == "mp":
            amt = int(data.get("amount", 0))
            await _grant_mp(db, tu, amt)
            await db.execute(
                "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
                (tu, "admin_mp_adjust", int(amt), json.dumps({"by": int(admin_id)}, ensure_ascii=False), int(now)),
            )

        elif kind == "ess":
            amt = int(data.get("amount", 0))
            await _grant_ess(db, tu, amt)
            await db.execute(
                "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
                (tu, "admin_ess_adjust", int(amt), json.dumps({"by": int(admin_id)}, ensure_ascii=False), int(now)),
            )

        elif kind == "item":
            item_id = int(data.get("arg1", 0))
            qty = int(data.get("qty", 0))
            await _grant_item(db, tu, item_id, qty)
            await db.execute(
                "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
                (tu, "admin_item_adjust", int(qty), json.dumps({"by": int(admin_id), "item_id": item_id}, ensure_ascii=False), int(now)),
            )

        elif kind == "cat":
            cat_id = int(data.get("arg1", 0))
            out = await _grant_cat_dup_logic(db, tu, cat_id)
            if not out.get("ok"):
                return "cat_id نامعتبر است.", admin_menu_keyboard()
            await db.execute(
                "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,?)",
                (int(admin_id), "admin_grant_cat", json.dumps({"target": tu, "cat_id": cat_id, "out": out}, ensure_ascii=False), int(now)),
            )
        else:
            return "نوع نامعتبر.", admin_menu_keyboard()

        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,?)",
            (int(admin_id), "admin_grant", json.dumps(data, ensure_ascii=False), int(now)),
        )
        await db.commit()
    finally:
        await db.close()

    context.user_data.pop("admin_grant", None)
    return "انجام شد.", admin_menu_keyboard()


# ----------------------------
# Ban/Unban
# ----------------------------
def _ban_key(user_id: int) -> str:
    return f"ban:user:{int(user_id)}"


def admin_ban_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Ban", callback_data="admin:ban:do")],
            [InlineKeyboardButton("Unban", callback_data="admin:ban:undo")],
            [InlineKeyboardButton("Cancel", callback_data="admin:ban:cancel")],
        ]
    )


async def admin_ban_start(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    if not _is_owner(user_id):
        return "دسترسی ندارید.", admin_menu_keyboard()
    context.user_data["admin_ban"] = {"step": "pick", "data": {}}
    return "Ban/Unban\n\nعملیات را انتخاب کن.", admin_ban_kb()


async def admin_ban_cancel(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    context.user_data.pop("admin_ban", None)
    return "لغو شد.", admin_menu_keyboard()


async def admin_ban_pick(mode: str, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    st = context.user_data.get("admin_ban") or {"data": {}}
    st["data"] = {"mode": mode}
    st["step"] = "user_id"
    context.user_data["admin_ban"] = st
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:ban:cancel")]])
    return "user_id را بفرست (عدد).", kb


async def admin_ban_handle_message(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[tuple[str, InlineKeyboardMarkup]]:
    st = context.user_data.get("admin_ban")
    if not st:
        return None
    if not _is_owner(user_id):
        return ("دسترسی ندارید.", admin_menu_keyboard())

    msg = update.message
    if not msg or not msg.text:
        return ("متن لازم است.", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:ban:cancel")]]))

    step = st.get("step")
    data = st.get("data", {})
    kb_cancel = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin:ban:cancel")]])

    if step == "user_id":
        try:
            tu = int(msg.text.strip())
        except Exception:
            return ("user_id نامعتبر است.", kb_cancel)
        data["target_user_id"] = tu
        st["data"] = data
        mode = data.get("mode")
        if mode == "do":
            st["step"] = "reason"
            return ("reason را بفرست (یا -).", kb_cancel)
        st["step"] = "confirm"
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Confirm", callback_data="admin:ban:confirm")],
                [InlineKeyboardButton("Cancel", callback_data="admin:ban:cancel")],
            ]
        )
        await msg.reply_text(f"Preview\n\nUnban user_id: {tu}", reply_markup=kb)
        return ("Preview ارسال شد.", kb)

    if step == "reason":
        reason = msg.text.strip()
        if reason == "-":
            reason = ""
        data["reason"] = reason
        st["data"] = data
        st["step"] = "confirm"
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Confirm", callback_data="admin:ban:confirm")],
                [InlineKeyboardButton("Cancel", callback_data="admin:ban:cancel")],
            ]
        )
        await msg.reply_text(
            f"Preview\n\nBan user_id: {data['target_user_id']}\nReason: {data.get('reason') or '-'}",
            reply_markup=kb,
        )
        return ("Preview ارسال شد.", kb)

    return None


async def admin_ban_confirm(admin_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
    st = context.user_data.get("admin_ban")
    if not st or st.get("step") != "confirm":
        return "چیزی برای تایید نیست.", admin_menu_keyboard()
    if not _is_owner(admin_id):
        return "دسترسی ندارید.", admin_menu_keyboard()

    data = st.get("data", {})
    mode = data.get("mode")
    tu = int(data.get("target_user_id", 0))
    now = _now()

    if mode == "do":
        payload = {"reason": data.get("reason", ""), "ts": int(now)}
        await set_config(_ban_key(tu), json.dumps(payload, ensure_ascii=False))
        action = "ban"
    else:
        db = await open_db()
        try:
            await db.execute("DELETE FROM config WHERE key=?", (_ban_key(tu),))
            await db.commit()
        finally:
            await db.close()
        action = "unban"

    db = await open_db()
    try:
        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,?)",
            (int(admin_id), f"admin_{action}", json.dumps({"target": tu}, ensure_ascii=False), int(now)),
        )
        await db.commit()
    finally:
        await db.close()

    context.user_data.pop("admin_ban", None)
    return "انجام شد.", admin_menu_keyboard()


async def is_banned(user_id: int) -> bool:
    v = await get_config(_ban_key(user_id))
    return v is not None


# ----------------------------
# Logs
# ----------------------------
async def admin_logs_page(page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    page = max(0, int(page))
    limit = 15
    offset = page * limit

    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT admin_id, action, ts, meta_json FROM admin_logs ORDER BY id DESC LIMIT ? OFFSET ?",
            (int(limit), int(offset)),
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    if not rows and page == 0:
        return "Logs\n\n(هیچ)", InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="nav:admin")]])

    lines = ["Logs\n"]
    for r in rows:
        ts = int(r["ts"] or 0)
        t = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "-"
        lines.append(f"- {t} | {r['action']} | admin:{r['admin_id']}")

    kb_rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"admin:logs:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data="nav:admin"))
    if len(rows) == limit:
        nav.append(InlineKeyboardButton("Next", callback_data=f"admin:logs:{page+1}"))
    kb_rows.append(nav)

    return "\n".join(lines), InlineKeyboardMarkup(kb_rows)
