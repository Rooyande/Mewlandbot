import time
from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import open_db

PAGE_SIZE = 6


def _now() -> int:
    return int(time.time())


def _fmt_ts(ts: int | None) -> str:
    if not ts:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))
    except Exception:
        return "-"


async def events_root_text() -> str:
    return "Events"


def events_root_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Active/Upcoming", callback_data="ev:list:0")],
            [InlineKeyboardButton("Back", callback_data="nav:home")],
        ]
    )


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
              AND rarity != 'Divine'
              AND (available_from IS NOT NULL OR available_until IS NOT NULL)
              AND (available_until IS NULL OR available_until >= ?)
            ORDER BY
              CASE WHEN available_from IS NULL THEN 0 ELSE 1 END DESC,
              available_from ASC,
              available_until ASC,
              cat_id DESC
            """,
            (int(now),),
        )
        rows = await cur.fetchall()

        items = []
        for r in rows:
            items.append(
                {
                    "cat_id": int(r["cat_id"]),
                    "name": str(r["name"]),
                    "rarity": str(r["rarity"]),
                    "available_from": r["available_from"],
                    "available_until": r["available_until"],
                    "pools_enabled": str(r["pools_enabled"] or ""),
                }
            )

        start = page * PAGE_SIZE
        chunk = items[start : start + PAGE_SIZE + 1]
        has_next = len(chunk) > PAGE_SIZE
        chunk = chunk[:PAGE_SIZE]
        has_prev = page > 0
        return chunk, has_prev, has_next
    finally:
        await db.close()


async def events_list_text(page: int) -> str:
    return f"Events\n\nPage: {int(page) + 1}"


def events_list_kb(items: List[dict], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    rows = []
    now = _now()

    for it in items:
        af = it.get("available_from")
        au = it.get("available_until")
        status = "Active"
        if af and int(af) > now:
            status = "Upcoming"
        label = f"{it['name']} ({it['rarity']}) • {status}"
        rows.append([InlineKeyboardButton(label, callback_data=f"ev:open:{it['cat_id']}:{page}")])

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"ev:list:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data="ev:root"))
    if has_next:
        nav.append(InlineKeyboardButton("Next", callback_data=f"ev:list:{page+1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton("Home", callback_data="nav:home")])
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

        name = str(r["name"])
        desc = str(r["description"])
        rarity = str(r["rarity"])
        af = r["available_from"]
        au = r["available_until"]
        pools = str(r["pools_enabled"] or "")

        status = "Active"
        if af and int(af) > now:
            status = "Upcoming"

        return (
            "Event Cat\n\n"
            f"{name} ({rarity})\n"
            f"Status: {status}\n"
            f"From: {_fmt_ts(af)}\n"
            f"Until: {_fmt_ts(au)}\n"
            f"Pools: {pools}\n\n"
            f"{desc}"
        )
    finally:
        await db.close()


def event_cat_kb(cat_id: int, back_page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Back", callback_data=f"ev:list:{int(back_page)}")],
            [InlineKeyboardButton("Shop", callback_data="nav:shop")],
            [InlineKeyboardButton("Home", callback_data="nav:home")],
        ]
    )
