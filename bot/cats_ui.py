import time
from typing import List, Tuple, Optional, Dict, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import open_db


PAGE_SIZE = 6


def cats_list_keyboard(rows: List[tuple], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    buttons = []
    for uc_id, name, rarity, level in rows:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{name} • {rarity} • L{level}",
                    callback_data=f"cat:open:{uc_id}",
                )
            ]
        )

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"cat:list:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data="nav:home"))
    if has_next:
        nav.append(InlineKeyboardButton("Next", callback_data=f"cat:list:{page+1}"))
    buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def cat_details_keyboard(user_cat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Feed", callback_data=f"cat:feed:{user_cat_id}"),
                InlineKeyboardButton("Play", callback_data=f"cat:play:{user_cat_id}"),
            ],
            [
                InlineKeyboardButton("Back to My Cats", callback_data="cat:list:0"),
                InlineKeyboardButton("Home", callback_data="nav:home"),
            ],
        ]
    )


async def fetch_user_cats_page(user_id: int, page: int) -> Tuple[List[tuple], bool, bool]:
    offset = max(0, page) * PAGE_SIZE

    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT
              uc.id AS user_cat_id,
              cc.name AS name,
              cc.rarity AS rarity,
              uc.level AS level
            FROM user_cats uc
            JOIN cats_catalog cc ON cc.cat_id = uc.cat_id
            WHERE uc.user_id=? AND uc.status='active'
            ORDER BY
              CASE LOWER(cc.rarity)
                WHEN 'common' THEN 1
                WHEN 'uncommon' THEN 2
                WHEN 'rare' THEN 3
                WHEN 'epic' THEN 4
                WHEN 'legendary' THEN 5
                WHEN 'mythic' THEN 6
                WHEN 'divine' THEN 7
                ELSE 99
              END ASC,
              uc.level DESC,
              cc.name ASC
            LIMIT ? OFFSET ?
            """,
            (user_id, PAGE_SIZE + 1, offset),
        )
        rows = await cur.fetchall()

        has_next = len(rows) > PAGE_SIZE
        rows = rows[:PAGE_SIZE]

        has_prev = page > 0

        out = [(int(r["user_cat_id"]), str(r["name"]), str(r["rarity"]), int(r["level"])) for r in rows]
        return out, has_prev, has_next
    finally:
        await db.close()


async def render_user_cats_page_text(user_id: int, page: int) -> str:
    rows, _, _ = await fetch_user_cats_page(user_id, page)
    if not rows:
        return "My Cats\n\nهیچ گربه فعالی ندارید."
    return f"My Cats\n\nPage: {page + 1}"


async def fetch_cat_media(user_id: int, user_cat_id: int) -> Optional[Dict[str, str]]:
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT cc.media_type, cc.media_file_id
            FROM user_cats uc
            JOIN cats_catalog cc ON cc.cat_id = uc.cat_id
            WHERE uc.user_id=? AND uc.id=?
            """,
            (user_id, user_cat_id),
        )
        r = await cur.fetchone()
        if r is None:
            return None
        mt = str(r["media_type"] or "").strip().lower()
        mf = str(r["media_file_id"] or "").strip()
        if not mt or not mf:
            return None
        return {"media_type": mt, "media_file_id": mf}
    finally:
        await db.close()


async def render_cat_details(user_id: int, user_cat_id: int) -> str:
    now = int(time.time())
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT
              uc.id AS user_cat_id,
              uc.level,
              uc.dup_counter,
              uc.status,
              uc.last_feed_at,
              uc.last_play_at,
              cc.cat_id,
              cc.name,
              cc.description,
              cc.rarity,
              cc.base_passive_rate
            FROM user_cats uc
            JOIN cats_catalog cc ON cc.cat_id = uc.cat_id
            WHERE uc.user_id=? AND uc.id=?
            """,
            (user_id, user_cat_id),
        )
        r = await cur.fetchone()
        if r is None:
            return "گربه پیدا نشد."

        lf = r["last_feed_at"]
        lp = r["last_play_at"]

        lf_txt = "never" if lf is None else f"{max(0, now - int(lf))}s ago"
        lp_txt = "never" if lp is None else f"{max(0, now - int(lp))}s ago"

        return (
            "Cat Details\n\n"
            f"Name: {r['name']}\n"
            f"Rarity: {r['rarity']}\n"
            f"Level: {int(r['level'] or 1)}\n"
            f"Dups: {int(r['dup_counter'] or 0)}\n"
            f"Base Passive: {float(r['base_passive_rate'] or 0.0)} MP/h\n\n"
            f"Last Feed: {lf_txt}\n"
            f"Last Play: {lp_txt}\n\n"
            f"{r['description']}"
        )
    finally:
        await db.close()
