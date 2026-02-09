import time
from typing import List, Tuple, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import open_db


PAGE_SIZE = 6


def _now() -> int:
    return int(time.time())


def events_root_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Active Events", callback_data="ev:list:0")],
            [InlineKeyboardButton("Back", callback_data="nav:home")],
        ]
    )


async def events_root_text() -> str:
    return "Events"


async def fetch_events_page(page: int) -> Tuple[List[dict], bool, bool]:
    page = max(0, int(page))
    now = _now()

    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT cat_id, name, rarity, available_from, available_until, pools_enabled
            FROM cats_catalog
            WHERE active=1
              AND available_until IS NOT NULL
              AND (available_from IS NULL OR available_from <= ?)
              AND available_until >= ?
            ORDER BY available_until ASC, cat_id ASC
            """,
            (now, now),
        )
        rows = await cur.fetchall()

        all_items = []
        for r in rows:
            all_items.append(
                {
                    "cat_id": int(r["cat_id"]),
                    "name": str(r["name"]),
                    "rarity": str(r["rarity"]),
                    "available_until": int(r["available_until"]),
                    "pools_enabled": str(r["pools_enabled"] or ""),
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


async def events_list_text(page: int) -> str:
    return f"Active Events\n\nPage: {int(page) + 1}"


def events_list_kb(items: List[dict], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    rows = []
    now = _now()

    for it in items:
        left = max(0, int(it["available_until"]) - now)
        hrs = left // 3600
        label = f"{it['name']} ({it['rarity']}) • {hrs}h"
        rows.append([InlineKeyboardButton(label, callback_data=f"ev:open:{it['cat_id']}:{page}")])

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"ev:list:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data="ev:root"))
    if has_next:
        nav.append(InlineKeyboardButton("Next", callback_data=f"ev:list:{page+1}"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)


async def event_cat_text(cat_id: int) -> str:
    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT name, description, rarity, available_from, available_until, pools_enabled
            FROM cats_catalog
            WHERE cat_id=? AND active=1
            """,
            (int(cat_id),),
        )
        r = await cur.fetchone()
        if r is None:
            return "Not found."

        until_ts = r["available_until"]
        left = 0
        if until_ts is not None:
            left = max(0, int(until_ts) - now)
        hrs = left // 3600

        pools = str(r["pools_enabled"] or "")
        return (
            "Event Cat\n\n"
            f"Name: {r['name']}\n"
            f"Rarity: {r['rarity']}\n"
            f"Pools: {pools}\n"
            f"Ends in: {hrs}h\n\n"
            f"{r['description']}"
        )
    finally:
        await db.close()


def event_cat_kb(cat_id: int, back_page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Back", callback_data=f"ev:list:{back_page}")],
            [InlineKeyboardButton("Home", callback_data="nav:home")],
        ]
    )
