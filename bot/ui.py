import time
from typing import Dict, Tuple, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db import open_db

DEFAULT_PASSIVE_CAP_HOURS = 24

PLAY_DEADLINE_DAYS = {
    "common": 2,
    "uncommon": 3,
    "rare": 4,
    "epic": 6,
    "legendary": 9,
    "mythic": 13,
    "divine": 10**9,
}

FEED_DEADLINE_DAYS = {
    "common": 2,
    "uncommon": 3,
    "rare": 5,
    "epic": 7,
    "legendary": 10,
    "mythic": 14,
    "divine": 10**9,
}


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Meow", callback_data="act:meow")],
            [
                InlineKeyboardButton("Feed All", callback_data="nav:feedall"),
                InlineKeyboardButton("Play All", callback_data="nav:playall"),
            ],
            [InlineKeyboardButton("My Cats", callback_data="nav:cats")],
            [
                InlineKeyboardButton("Inventory", callback_data="nav:inv"),
                InlineKeyboardButton("Shop", callback_data="nav:shop"),
            ],
            [
                InlineKeyboardButton("Events", callback_data="nav:events"),
                InlineKeyboardButton("Settings", callback_data="nav:settings"),
            ],
        ]
    )


def back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="nav:home")]])


def _fmt_dhms(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d > 0:
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


async def _get_config_float(db, key: str, default: float) -> float:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return default
    try:
        return float(row["value"])
    except Exception:
        return default


async def _get_rarity_mults(db) -> Dict[str, float]:
    cur = await db.execute("SELECT key, value FROM config WHERE key LIKE 'rarity_mult_%'")
    rows = await cur.fetchall()
    out: Dict[str, float] = {}
    for r in rows:
        k = str(r["key"])
        v = r["value"]
        rarity = k.replace("rarity_mult_", "").strip().lower()
        try:
            out[rarity] = float(v)
        except Exception:
            pass
    return out


async def _calc_passive_rate_per_hour(db, user_id: int) -> float:
    level_bonus = await _get_config_float(db, "level_bonus", 0.0)
    rarity_mults = await _get_rarity_mults(db)

    cur = await db.execute(
        """
        SELECT cc.rarity, cc.base_passive_rate, uc.level
        FROM user_cats uc
        JOIN cats_catalog cc ON cc.cat_id = uc.cat_id
        WHERE uc.user_id=? AND uc.status='active'
        """,
        (user_id,),
    )
    rows = await cur.fetchall()

    total = 0.0
    for r in rows:
        rarity = str(r["rarity"] or "").strip().lower()
        base_rate = float(r["base_passive_rate"] or 0.0)
        level = int(r["level"] or 1)

        rarity_mult = float(rarity_mults.get(rarity, 1.0))
        level_mult = 1.0 + (level_bonus * max(0, level - 1))
        item_mult = 1.0

        total += base_rate * rarity_mult * level_mult * item_mult

    return total


async def _nearest_deadlines(db, user_id: int, now: int) -> Tuple[Optional[int], Optional[int]]:
    cur = await db.execute(
        """
        SELECT cc.rarity, uc.last_feed_at, uc.last_play_at
        FROM user_cats uc
        JOIN cats_catalog cc ON cc.cat_id = uc.cat_id
        WHERE uc.user_id=? AND uc.status='active'
        """,
        (user_id,),
    )
    rows = await cur.fetchall()

    nearest_feed: Optional[int] = None
    nearest_play: Optional[int] = None

    for r in rows:
        rarity = str(r["rarity"] or "").strip().lower()

        feed_days = FEED_DEADLINE_DAYS.get(rarity, 2)
        play_days = PLAY_DEADLINE_DAYS.get(rarity, 2)

        lf = r["last_feed_at"]
        lp = r["last_play_at"]

        if lf is not None:
            due = int(lf) + int(feed_days * 86400)
            remain = due - now
            if nearest_feed is None or remain < nearest_feed:
                nearest_feed = remain
        else:
            if nearest_feed is None or 0 < nearest_feed:
                nearest_feed = 0

        if lp is not None:
            due = int(lp) + int(play_days * 86400)
            remain = due - now
            if nearest_play is None or remain < nearest_play:
                nearest_play = remain
        else:
            if nearest_play is None or 0 < nearest_play:
                nearest_play = 0

    return nearest_feed, nearest_play


async def render_home_text(user_id: int) -> str:
    now = int(time.time())
    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT mp_balance, shelter_level, passive_cap_hours, last_passive_ts FROM users WHERE user_id=?",
            (user_id,),
        )
        u = await cur.fetchone()

        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (user_id,))
        r = await cur.fetchone()

        cur = await db.execute(
            "SELECT COUNT(1) AS c FROM user_cats WHERE user_id=? AND status='active'",
            (user_id,),
        )
        c = await cur.fetchone()

        mp = 0 if u is None else int(u["mp_balance"] or 0)
        shelter = 1 if u is None else int(u["shelter_level"] or 1)
        cap_hours = None if u is None else u["passive_cap_hours"]
        cap_hours = int(cap_hours) if cap_hours is not None else DEFAULT_PASSIVE_CAP_HOURS
        last_ts = now if u is None else int(u["last_passive_ts"] or now)

        essence = 0 if r is None else int(r["essence"] or 0)
        cats = 0 if c is None else int(c["c"] or 0)

        rate_h = await _calc_passive_rate_per_hour(db, user_id)

        stored_sec = max(0, now - last_ts)
        cap_sec = max(0, cap_hours) * 3600
        stored_used = stored_sec if cap_sec == 0 else min(stored_sec, cap_sec)
        to_cap = 0 if cap_sec == 0 else max(0, cap_sec - stored_used)

        nearest_feed, nearest_play = await _nearest_deadlines(db, user_id, now)
        feed_txt = "N/A" if nearest_feed is None else ("OVERDUE" if nearest_feed <= 0 else _fmt_dhms(nearest_feed))
        play_txt = "N/A" if nearest_play is None else ("OVERDUE" if nearest_play <= 0 else _fmt_dhms(nearest_play))

        return (
            "Home\n\n"
            f"MP: {mp}\n"
            f"Essence: {essence}\n"
            f"Shelter: {shelter}\n"
            f"Active Cats: {cats}\n\n"
            f"Passive Rate: {rate_h:.3f} MP/h\n"
            f"Passive Stored: {_fmt_dhms(stored_used)} / {cap_hours}h\n"
            f"Time to Cap: {_fmt_dhms(to_cap)}\n\n"
            f"Next Feed: {feed_txt}\n"
            f"Next Play: {play_txt}"
        )
    finally:
        await db.close()
