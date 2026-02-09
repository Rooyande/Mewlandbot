import json
from dataclasses import dataclass
from typing import Optional, Dict, Any

from telegram import Update
from telegram.ext import ContextTypes

from db import open_db


WZ_KEY = "admin_additem"


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
    return bool(ctx.user_data.get(WZ_KEY))


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


async def admin_additem_start(admin_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    d = AddItemDraft()
    _draft_set(context, d)
    return "Add Item\n\nName را ارسال کنید."


async def admin_additem_cancel(context: ContextTypes.DEFAULT_TYPE) -> str:
    _draft_clear(context)
    return "لغو شد."


async def admin_additem_preview(context: ContextTypes.DEFAULT_TYPE) -> str:
    d = _draft_get(context)
    return (
        "Add Item Preview\n\n"
        f"Name: {d.name}\n"
        f"Type: {d.type}\n"
        f"Tradable: {d.tradable}\n"
        f"Active: {d.active}\n\n"
        f"Effect JSON:\n{d.effect_json}\n\n"
        f"Durability JSON:\n{d.durability_rules_json}\n\n"
        "Confirm / Cancel"
    )


async def admin_additem_handle_message(admin_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    if not _is_running(context):
        return None

    if not update.message or update.message.text is None:
        return "فقط متن ارسال کنید."

    text = update.message.text.strip()
    d = _draft_get(context)
    nf = _next_field(d)

    if nf == "name":
        if len(text) < 2:
            return "Name نامعتبر است. دوباره ارسال کنید."
        d.name = text
        _draft_set(context, d)
        return "Type را ارسال کنید. (مثلاً utility یا cosmetic)"

    if nf == "type":
        if len(text) < 2:
            return "Type نامعتبر است. دوباره ارسال کنید."
        d.type = text
        _draft_set(context, d)
        return "Effect JSON را ارسال کنید. (یا 'none')"

    if nf == "effect_json":
        if text.lower() == "none":
            d.effect_json = ""
        else:
            try:
                json.loads(text)
                d.effect_json = text
            except Exception:
                return "Effect JSON نامعتبر است. JSON صحیح یا 'none' ارسال کنید."
        _draft_set(context, d)
        return "Durability Rules JSON را ارسال کنید. (یا 'none')"

    if nf == "durability_rules_json":
        if text.lower() == "none":
            d.durability_rules_json = ""
        else:
            try:
                json.loads(text)
                d.durability_rules_json = text
            except Exception:
                return "Durability JSON نامعتبر است. JSON صحیح یا 'none' ارسال کنید."
        _draft_set(context, d)
        return "Tradable را ارسال کنید. (0 یا 1)"

    if nf == "tradable":
        if text not in ("0", "1"):
            return "Tradable فقط 0 یا 1."
        d.tradable = int(text)
        _draft_set(context, d)
        return "Active را ارسال کنید. (0 یا 1)"

    if nf == "active":
        if text not in ("0", "1"):
            return "Active فقط 0 یا 1."
        d.active = int(text)
        _draft_set(context, d)
        return await admin_additem_preview(context)

    return await admin_additem_preview(context)


async def admin_additem_confirm(admin_id: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    d = _draft_get(context)
    if _next_field(d) != "done":
        return "Wizard کامل نیست."

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
                d.effect_json or "",
                d.durability_rules_json or "",
                int(d.tradable or 0),
                int(d.active or 1),
            ),
        )
        item_id = cur.lastrowid

        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,strftime('%s','now'))",
            (
                admin_id,
                "add_item",
                json.dumps(
                    {
                        "item_id": int(item_id),
                        "name": d.name,
                        "type": d.type,
                        "tradable": int(d.tradable or 0),
                        "active": int(d.active or 1),
                    },
                    ensure_ascii=False,
                ),
            ),
        )

        await db.commit()
        _draft_clear(context)
        return f"Item added.\n\nitem_id: {int(item_id)}"
    finally:
        await db.close()
