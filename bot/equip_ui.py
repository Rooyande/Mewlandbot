import json
from typing import List, Tuple, Optional, Dict, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import open_db
from equip import get_user_cat_equipped


PAGE_SIZE = 6


async def _equipped_item_ids(user_id: int, user_cat_id: int) -> List[int]:
    eq = await get_user_cat_equipped(user_id, user_cat_id)
    if not eq:
        return []
    out = []
    for s in eq.get("slots", []):
        try:
            out.append(int(s.get("item_id", 0)))
        except Exception:
            pass
    return [x for x in out if x > 0]


async def fetch_equipable_items_page(user_id: int, user_cat_id: int, page: int) -> Tuple[List[dict], bool, bool]:
    equipped_ids = set(await _equipped_item_ids(user_id, user_cat_id))
    page = max(0, int(page))

    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT ic.item_id, ic.name, ic.type, ui.qty
            FROM user_items ui
            JOIN items_catalog ic ON ic.item_id = ui.item_id
            WHERE ui.user_id=?
              AND ui.qty > 0
              AND COALESCE(ic.active,1)=1
            ORDER BY ic.type ASC, ic.name ASC
            """,
            (user_id,),
        )
        rows = await cur.fetchall()

        all_items = []
        for r in rows:
            iid = int(r["item_id"])
            all_items.append(
                {
                    "item_id": iid,
                    "name": str(r["name"]),
                    "type": str(r["type"] or ""),
                    "qty": int(r["qty"] or 0),
                    "equipped": iid in equipped_ids,
                }
            )

        start = page * PAGE_SIZE
        chunk = all_items[start : start + PAGE_SIZE + 1]

        has_next = len(chunk) > PAGE_SIZE
        chunk = chunk[:PAGE_SIZE]
        has_prev = page > 0

        return chunk, has_prev, has_next
    finally:
        await db.close()


async def equipped_summary_text(user_id: int, user_cat_id: int) -> str:
    eq = await get_user_cat_equipped(user_id, user_cat_id)
    if not eq:
        return "Equipped Items\n\n(هیچ)"
    ids = [int(s.get("item_id", 0)) for s in eq.get("slots", []) if int(s.get("item_id", 0)) > 0]
    if not ids:
        return "Equipped Items\n\n(هیچ)"
    return "Equipped Items\n\n" + ", ".join(str(i) for i in ids)


def equip_menu_kb(user_cat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Equip", callback_data=f"eq:list:{user_cat_id}:0")],
            [InlineKeyboardButton("Back", callback_data=f"cat:open:{user_cat_id}")],
        ]
    )


async def equip_list_text(user_cat_id: int, page: int) -> str:
    return f"Equip Item\n\nPage: {page + 1}"


def equip_list_kb(user_cat_id: int, items: List[dict], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    rows = []
    for it in items:
        label = f"{it['name']} • x{it['qty']}"
        if it.get("equipped"):
            label = f"✅ {label}"
            rows.append([InlineKeyboardButton(label, callback_data=f"eq:uneq:{user_cat_id}:{it['item_id']}")])
        else:
            rows.append([InlineKeyboardButton(label, callback_data=f"eq:eq:{user_cat_id}:{it['item_id']}")])

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"eq:list:{user_cat_id}:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data=f"cat:open:{user_cat_id}"))
    if has_next:
        nav.append(InlineKeyboardButton("Next", callback_data=f"eq:list:{user_cat_id}:{page+1}"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)
