import json
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import OWNER_ID
from db import open_db


WZ_KEY = "admin_additem"


def _now() -> int:
    return int(time.time())


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


@dataclass
class AddItemDraft:
    name: str | None = None
    type: str | None = None
    effect_json: str | None = None
    durability_rules_json: str | None = None
    tradable: int | None = None
    active: int | None = None


def _draft_get(ctx: ContextTypes.DEFAULT_TYPE) -> AddItemDraft:
    raw = ctx.user_data.get(WZ_KEY)
    if isinstance(raw, dict):
        return AddItemDraft(**raw)
    return AddItemDraft()


def _draft_set(ctx: ContextTypes.DEFAULT_TYPE, d: AddItemDraft) -> None:
    ctx.user_data[WZ_KEY] = {
        "name": d.name,
        "type": d.type,
        "effect_json": d.effect_json,
        "durability_rules_json": d.durability_rules_json,
        "tradable": d.tradable,
        "active": d.active,
    }


def _draft_clear(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop(WZ_KEY, None)


def _is_running(ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    return WZ_KEY in ctx.user_data


def _next_field(d: AddItemDraft) -> str:
    if not d.name:
        return "name"
    if not d.type:
        return "type"
    if d.effect_json is None:
        return "effect_json"
    if d.durability_rules_json is None:
        return "durability_rules_json"
    if d.tradable is None:
        return "tradable"
    if d.active is None:
        return "active"
    return "done"


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm", callback_data="admin:additem:confirm")],
            [InlineKeyboardButton("Cancel", callback_data="admin:additem:cancel")],
        ]
    )


async def admin_additem_start(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup | None]:
    if not _is_owner(user_id):
        return ("دسترسی ندارید.", None)
    _draft_set(context, AddItemDraft())
    return ("Add Item\n\nName را ارسال کنید.", None)


async def admin_additem_cancel(context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup | None]:
    _draft_clear(context)
    return ("لغو شد.", None)


async def _preview(context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup]:
    d = _draft_get(context)
    txt = (
        "Add Item Preview\n\n"
        f"Name: {d.name}\n"
        f"Type: {d.type}\n"
        f"Tradable: {d.tradable}\n"
        f"Active: {d.active}\n\n"
        f"Effect JSON:\n{d.effect_json}\n\n"
        f"Durability JSON:\n{d.durability_rules_json}\n"
    )
    return txt, _confirm_kb()


async def admin_additem_handle_message(
    user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[Tuple[str, InlineKeyboardMarkup | None]]:
    if not _is_running(context):
        return None
    if not _is_owner(user_id):
        return ("دسترسی ندارید.", None)

    if not update.message or update.message.text is None:
        return ("فقط متن ارسال کنید.", None)

    text = update.message.text.strip()
    d = _draft_get(context)
    nf = _next_field(d)

    if nf == "name":
        if len(text) < 2:
            return ("Name نامعتبر است.", None)
        d.name = text
        _draft_set(context, d)
        return ("Type را ارسال کنید. (مثلاً utility یا cosmetic)", None)

    if nf == "type":
        if len(text) < 2:
            return ("Type نامعتبر است.", None)
        d.type = text
        _draft_set(context, d)
        return ("Effect JSON را ارسال کنید. (یا 'none')", None)

    if nf == "effect_json":
        if text.lower() == "none":
            d.effect_json = "{}"
        else:
            try:
                json.loads(text)
            except Exception:
                return ("Effect JSON نامعتبر است.", None)
            d.effect_json = text
        _draft_set(context, d)
        return ("Durability Rules JSON را ارسال کنید. (یا 'none')", None)

    if nf == "durability_rules_json":
        if text.lower() == "none":
            d.durability_rules_json = "{}"
        else:
            try:
                json.loads(text)
            except Exception:
                return ("Durability JSON نامعتبر است.", None)
            d.durability_rules_json = text
        _draft_set(context, d)
        return ("Tradable را ارسال کنید. (0 یا 1)", None)

    if nf == "tradable":
        if text not in ("0", "1"):
            return ("Tradable فقط 0 یا 1.", None)
        d.tradable = int(text)
        _draft_set(context, d)
        return ("Active را ارسال کنید. (0 یا 1)", None)

    if nf == "active":
        if text not in ("0", "1"):
            return ("Active فقط 0 یا 1.", None)
        d.active = int(text)
        _draft_set(context, d)
        return await _preview(context)

    return await _preview(context)


async def admin_additem_confirm(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup | None]:
    if not _is_owner(user_id):
        return ("دسترسی ندارید.", None)

    d = _draft_get(context)
    if _next_field(d) != "done":
        return ("Wizard کامل نیست.", None)

    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            """
            INSERT INTO items_catalog(name, type, effect_json, durability_rules_json, tradable, active)
            VALUES(?,?,?,?,?,?)
            """,
            (
                d.name,
                d.type,
                d.effect_json or "{}",
                d.durability_rules_json or "{}",
                int(d.tradable or 0),
                int(d.active or 1),
            ),
        )
        item_id = int(cur.lastrowid)

        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,?)",
            (
                int(user_id),
                "add_item",
                json.dumps(
                    {
                        "item_id": item_id,
                        "name": d.name,
                        "type": d.type,
                        "tradable": int(d.tradable or 0),
                        "active": int(d.active or 1),
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    _draft_clear(context)
    return (f"ثبت شد.\n\nitem_id: {item_id}", None)
