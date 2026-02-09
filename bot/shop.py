import json
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from db import open_db

RARITY_ORDER = ["Common", "Uncommon", "Rare", "Epic"]

PRICE_MULTS = {
    "Common": 60,
    "Uncommon": 150,
    "Rare": 400,
    "Epic": 3500,
}

# default standard box price (can be overridden by config)
DEFAULT_STANDARD_PRICE = 10

# weekly cap (count) for direct purchases
DEFAULT_WEEKLY_CAP = 5


def _now() -> int:
    return int(time.time())


async def _cfg_int(key: str, default: int) -> int:
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
        row = await cur.fetchone()
        if row is None:
            return default
        try:
            return int(row["value"])
        except Exception:
            return default
    finally:
        await db.close()


async def _cfg_json(key: str) -> Optional[dict]:
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
        row = await cur.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["value"])
        except Exception:
            return None
    finally:
        await db.close()


async def _week_key(now_ts: int) -> str:
    # ISO week key
    import datetime as _dt

    dt = _dt.datetime.utcfromtimestamp(now_ts)
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w}"


@dataclass
class PurchaseResult:
    ok: bool
    reason: str = ""
    cat_id: int | None = None
    rarity: str | None = None
    name: str | None = None
    media_type: str | None = None
    media_file_id: str | None = None
    outcome: dict | None = None
    price: int = 0


async def list_shop_cats_by_rarity(rarity: str) -> List[dict]:
    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT cat_id, name, rarity, media_type, media_file_id
            FROM cats_catalog
            WHERE active=1
              AND rarity=?
              AND rarity != 'Divine'
              AND (
                available_from IS NULL OR available_from <= ?
              )
              AND (
                available_until IS NULL OR available_until >= ?
              )
              AND (
                ',' || pools_enabled || ',' LIKE '%,Shop,%'
              )
            ORDER BY name ASC
            """,
            (rarity, now, now),
        )
        rows = await cur.fetchall()
        return [
            {
                "cat_id": int(r["cat_id"]),
                "name": str(r["name"]),
                "rarity": str(r["rarity"]),
                "media_type": str(r["media_type"] or ""),
                "media_file_id": str(r["media_file_id"] or ""),
            }
            for r in rows
        ]
    finally:
        await db.close()


async def _direct_price_for_rarity(rarity: str) -> int:
    std_price = await _cfg_int("standard_price", DEFAULT_STANDARD_PRICE)
    mult = PRICE_MULTS.get(rarity, 60)
    return int(std_price * mult)


async def _weekly_count(user_id: int, now_ts: int) -> int:
    wk = await _week_key(now_ts)
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT COUNT(1) AS c
            FROM economy_logs
            WHERE user_id=?
              AND action='direct_buy'
              AND meta_json LIKE ?
            """,
            (user_id, f'%\"week\":\"{wk}\"%'),
        )
        r = await cur.fetchone()
        return 0 if r is None else int(r["c"] or 0)
    finally:
        await db.close()


async def direct_buy(user_id: int, cat_id: int) -> PurchaseResult:
    now = _now()
    wk = await _week_key(now)

    weekly_cap = await _cfg_int("direct_weekly_cap", DEFAULT_WEEKLY_CAP)
    used = await _weekly_count(user_id, now)
    if used >= weekly_cap:
        return PurchaseResult(False, "weekly_cap")

    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT cat_id, name, description, rarity, base_passive_rate, media_type, media_file_id, active, pools_enabled,
                   available_from, available_until
            FROM cats_catalog
            WHERE cat_id=? AND active=1
            """,
            (cat_id,),
        )
        cat = await cur.fetchone()
        if cat is None:
            return PurchaseResult(False, "not_found")

        rarity = str(cat["rarity"])
        if rarity not in RARITY_ORDER:
            return PurchaseResult(False, "not_allowed")

        # must be in Shop pool and in time window
        if ",Shop," not in f",{str(cat['pools_enabled'] or '')},":
            return PurchaseResult(False, "not_in_pool")

        af = cat["available_from"]
        au = cat["available_until"]
        if af is not None and int(af) > now:
            return PurchaseResult(False, "not_in_window")
        if au is not None and int(au) < now:
            return PurchaseResult(False, "not_in_window")

        price = await _direct_price_for_rarity(rarity)

        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (user_id,))
        u = await cur.fetchone()
        mp = 0 if u is None else int(u["mp_balance"] or 0)
        if mp < price:
            return PurchaseResult(False, "no_mp")

        await db.execute("UPDATE users SET mp_balance = mp_balance - ? WHERE user_id=?", (price, user_id))

        # add to user (new or dup)
        cur = await db.execute(
            "SELECT id, level, dup_counter, status FROM user_cats WHERE user_id=? AND cat_id=? ORDER BY id LIMIT 1",
            (user_id, int(cat["cat_id"])),
        )
        owned = await cur.fetchone()

        outcome: Dict[str, Any]
        if owned is None:
            await db.execute(
                """
                INSERT INTO user_cats(user_id, cat_id, level, dup_counter, status, last_feed_at, last_play_at, obtained_at)
                VALUES(?, ?, 1, 0, 'active', ?, ?, ?)
                """,
                (user_id, int(cat["cat_id"]), now, now, now),
            )
            outcome = {"type": "new"}
        else:
            level = int(owned["level"] or 1)
            dup = int(owned["dup_counter"] or 0)
            status = str(owned["status"] or "active")
            if status != "active":
                status = "active"

            max_level = await _cfg_int("max_level", 20)
            if level >= max_level:
                outcome = {"type": "dup_max", "level": level}
            else:
                # thresholds same as cats.py
                th = {"Common": 25, "Uncommon": 15, "Rare": 8, "Epic": 4}.get(rarity, 25)
                dup += 1
                level_up = False
                if dup >= th:
                    level += 1
                    dup = 0
                    level_up = True
                await db.execute(
                    "UPDATE user_cats SET level=?, dup_counter=?, status=? WHERE id=?",
                    (level, dup, status, int(owned["id"])),
                )
                outcome = {"type": "dup", "level": level, "level_up": level_up, "dup": dup, "threshold": th}

        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (
                user_id,
                "direct_buy",
                -int(price),
                json.dumps({"cat_id": int(cat["cat_id"]), "rarity": rarity, "week": wk}, ensure_ascii=False),
                now,
            ),
        )
        await db.commit()

        return PurchaseResult(
            True,
            cat_id=int(cat["cat_id"]),
            rarity=rarity,
            name=str(cat["name"]),
            media_type=str(cat["media_type"] or ""),
            media_file_id=str(cat["media_file_id"] or ""),
            outcome=outcome,
            price=price,
        )
    finally:
        await db.close()
