import json
from dataclasses import dataclass
from typing import Optional, Tuple, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db import open_db


WZ_OFFER_KEY = "admin_ishop_addoffer"
WZ_CAP_KEY = "admin_ishop_setcap"


@dataclass
class OfferDraft:
    item_id: int | None = None
    price: int | None = None
    active: int | None = None


def ishop_admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Add Offer", callback_data="admin:ishop:addoffer")],
            [InlineKeyboardButton("List Offers", callback_data="admin:ishop:list:0")],
            [InlineKeyboardButton("Set Weekly Cap", callback_data="admin:ishop:setcap")],
            [InlineKeyboardButton("Back", callback_data="nav:admin")],
        ]
    )


async def ishop_admin_menu_text() -> str:
    return "Admin • Item Shop"


def _offer_get(ctx: ContextTypes.DEFAULT_TYPE) -> OfferDraft:
    raw = ctx.user_data.get(WZ_OFFER_KEY)
    if isinstance(raw, dict):
        return OfferDraft(**raw)
    return OfferDraft()


def _offer_set(ctx: ContextTypes.DEFAULT_TYPE, d: OfferDraft) -> None:
    ctx.user_data[WZ_OFFER_KEY] = {"item_id": d.item_id, "price": d.price, "active": d.active}


def _offer_clear(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop(WZ_OFFER_KEY, None)


def _cap_running(ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(ctx.user_data.get(WZ_CAP_KEY))


def _cap_set_running(ctx: ContextTypes.DEFAULT_TYPE, on: bool) -> None:
    if on:
        ctx.user_data[WZ_CAP_KEY] = True
    else:
        ctx.user_data.pop(WZ_CAP_KEY, None)


def _offer_next(d: OfferDraft) -> str:
    if d.item_id is None:
        return "item_id"
    if d.price is None:
        return "price"
    if d.active is None:
        return "active"
    return "done"


def offer_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm", callback_data="admin:ishop:addoffer:confirm")],
            [InlineKeyboardButton("Cancel", callback_data="admin:ishop:addoffer:cancel")],
        ]
    )


async def add_offer_start(context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup | None]:
    _offer_set(context, OfferDraft())
    return "Add Offer\n\nitem_id را ارسال کنید.", None


async def add_offer_cancel(context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup | None]:
    _offer_clear(context)
    return "لغو شد.", ishop_admin_menu_kb()


async def add_offer_preview(context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup]:
    d = _offer_get(context)
    txt = (
        "Add Offer Preview\n\n"
        f"item_id: {d.item_id}\n"
        f"price: {d.price}\n"
        f"active: {d.active}\n"
    )
    return txt, offer_confirm_kb()


async def add_offer_handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[Tuple[str, InlineKeyboardMarkup | None]]:
    if WZ_OFFER_KEY not in context.user_data:
        return None
    if not update.message or update.message.text is None:
        return ("فقط متن ارسال کنید.", None)

    text = update.message.text.strip()
    d = _offer_get(context)
    nf = _offer_next(d)

    if nf == "item_id":
        try:
            item_id = int(text)
            if item_id <= 0:
                raise ValueError()
        except Exception:
            return ("item_id نامعتبر است.", None)

        db = await open_db()
        try:
            cur = await db.execute("SELECT item_id FROM items_catalog WHERE item_id=?", (item_id,))
            row = await cur.fetchone()
        finally:
            await db.close()

        if row is None:
            return ("item_id یافت نشد.", None)

        d.item_id = item_id
        _offer_set(context, d)
        return ("price (MP) را ارسال کنید.", None)

    if nf == "price":
        try:
            price = int(text)
            if price <= 0:
                raise ValueError()
        except Exception:
            return ("price نامعتبر است.", None)
        d.price = price
        _offer_set(context, d)
        return ("active را ارسال کنید. (0 یا 1)", None)

    if nf == "active":
        if text not in ("0", "1"):
            return ("active فقط 0 یا 1.", None)
        d.active = int(text)
        _offer_set(context, d)
        return await add_offer_preview(context)

    return await add_offer_preview(context)


async def add_offer_confirm(admin_id: int, context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup | None]:
    d = _offer_get(context)
    if _offer_next(d) != "done":
        return ("Wizard کامل نیست.", None)

    db = await open_db()
    try:
        cur = await db.execute("SELECT item_id FROM items_catalog WHERE item_id=?", (int(d.item_id),))
        row = await cur.fetchone()
        if row is None:
            return ("item_id یافت نشد.", ishop_admin_menu_kb())

        cur2 = await db.execute(
            """
            INSERT INTO item_shop_offers(item_id, price, active, created_at, updated_at)
            VALUES(?,?,?,strftime('%s','now'),strftime('%s','now'))
            """,
            (int(d.item_id), int(d.price), int(d.active)),
        )
        offer_id = int(cur2.lastrowid)

        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,strftime('%s','now'))",
            (
                int(admin_id),
                "item_shop_add_offer",
                json.dumps({"offer_id": offer_id, "item_id": int(d.item_id), "price": int(d.price), "active": int(d.active)}, ensure_ascii=False),
            ),
        )
        await db.commit()
        _offer_clear(context)
        return (f"Offer added.\n\noffer_id: {offer_id}", ishop_admin_menu_kb())
    finally:
        await db.close()


async def list_offers(page: int) -> Tuple[str, InlineKeyboardMarkup]:
    page = max(0, int(page))
    page_size = 7
    offset = page * page_size

    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT o.offer_id, o.item_id, o.price, o.active, c.name
            FROM item_shop_offers o
            JOIN items_catalog c ON c.item_id=o.item_id
            ORDER BY o.offer_id DESC
            LIMIT ? OFFSET ?
            """,
            (page_size + 1, offset),
        )
        rows = await cur.fetchall()
    finally:
        await db.close()

    has_next = len(rows) > page_size
    rows = rows[:page_size]
    has_prev = page > 0

    txt = f"Item Shop Offers\n\nPage: {page + 1}"
    kb_rows: List[List[InlineKeyboardButton]] = []

    for r in rows:
        offer_id = int(r["offer_id"])
        name = str(r["name"])
        price = int(r["price"])
        active = int(r["active"])
        status = "ON" if active == 1 else "OFF"
        kb_rows.append([InlineKeyboardButton(f"{name} • {price} • {status}", callback_data=f"admin:ishop:offer:{offer_id}")])

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"admin:ishop:list:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data="admin:ishop"))
    if has_next:
        nav.append(InlineKeyboardButton("Next", callback_data=f"admin:ishop:list:{page+1}"))
    kb_rows.append(nav)

    return txt, InlineKeyboardMarkup(kb_rows)


async def offer_detail(offer_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT o.offer_id, o.item_id, o.price, o.active, c.name, c.type
            FROM item_shop_offers o
            JOIN items_catalog c ON c.item_id=o.item_id
            WHERE o.offer_id=?
            """,
            (int(offer_id),),
        )
        r = await cur.fetchone()
    finally:
        await db.close()

    if r is None:
        return ("Not found.", ishop_admin_menu_kb())

    active = int(r["active"])
    status = "ON" if active == 1 else "OFF"

    txt = (
        "Offer Details\n\n"
        f"offer_id: {int(r['offer_id'])}\n"
        f"item_id: {int(r['item_id'])}\n"
        f"name: {str(r['name'])}\n"
        f"type: {str(r['type'])}\n"
        f"price: {int(r['price'])}\n"
        f"active: {status}\n"
    )

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Toggle Active", callback_data=f"admin:ishop:toggle:{int(r['offer_id'])}")],
            [InlineKeyboardButton("Back", callback_data="admin:ishop:list:0")],
        ]
    )
    return txt, kb


async def offer_toggle(admin_id: int, offer_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    db = await open_db()
    try:
        cur = await db.execute("SELECT active FROM item_shop_offers WHERE offer_id=?", (int(offer_id),))
        r = await cur.fetchone()
        if r is None:
            return ("Not found.", ishop_admin_menu_kb())

        new_active = 0 if int(r["active"]) == 1 else 1
        await db.execute(
            "UPDATE item_shop_offers SET active=?, updated_at=strftime('%s','now') WHERE offer_id=?",
            (new_active, int(offer_id)),
        )
        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,strftime('%s','now'))",
            (
                int(admin_id),
                "item_shop_toggle_offer",
                json.dumps({"offer_id": int(offer_id), "active": int(new_active)}, ensure_ascii=False),
            ),
        )
        await db.commit()
    finally:
        await db.close()

    return await offer_detail(int(offer_id))


async def set_weekly_cap_start(context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, InlineKeyboardMarkup | None]:
    _cap_set_running(context, True)
    return ("Weekly cap را ارسال کنید. (عدد)\n\nبرای غیرفعال: 0", None)


async def set_weekly_cap_handle_message(
    admin_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[Tuple[str, InlineKeyboardMarkup | None]]:
    if not _cap_running(context):
        return None
    if not update.message or update.message.text is None:
        return ("فقط متن ارسال کنید.", None)

    text = update.message.text.strip()
    try:
        cap = int(text)
        if cap < 0:
            raise ValueError()
    except Exception:
        return ("عدد نامعتبر است.", None)

    db = await open_db()
    try:
        await db.execute(
            "INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("item_shop_weekly_cap", str(cap)),
        )
        await db.execute(
            "INSERT INTO admin_logs(admin_id, action, meta_json, ts) VALUES(?,?,?,strftime('%s','now'))",
            (int(admin_id), "item_shop_set_weekly_cap", json.dumps({"cap": cap}, ensure_ascii=False)),
        )
        await db.commit()
    finally:
        await db.close()

    _cap_set_running(context, False)
    return (f"Saved.\n\nitem_shop_weekly_cap = {cap}", ishop_admin_menu_kb())
