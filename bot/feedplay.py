import json
import time
from dataclasses import dataclass
from typing import Dict, Any, List

from db import open_db


def _now() -> int:
    return int(time.time())


PLAY_DEADLINE_DAYS = {
    "Common": 2,
    "Uncommon": 3,
    "Rare": 4,
    "Epic": 6,
    "Legendary": 9,
    "Mythic": 13,
    "Divine": 10**9,
}

FEED_DEADLINE_DAYS = {
    "Common": 2,
    "Uncommon": 3,
    "Rare": 5,
    "Epic": 7,
    "Legendary": 10,
    "Mythic": 14,
    "Divine": 10**9,
}


async def _cfg_int(db, key: str, default: int) -> int:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return default
    try:
        return int(float(row["value"]))
    except Exception:
        return default


async def _cfg_days(db, key: str, default_days: int) -> int:
    v = await _cfg_int(db, key, default_days)
    return max(0, int(v))


@dataclass
class FeedPlayResult:
    ok: bool
    reason: str = ""
    mp_spent: int = 0
    affected: int = 0


async def apply_survival(user_id: int) -> None:
    """
    قوانین:
    - اگر feed از deadline رد شود => dead
    - اگر play از deadline رد شود => runaway
    - runaway بعد از recover_window حذف می‌شود
    - dead بعد از dead_archive_hours حذف می‌شود
    نکته: برای ذخیره timestamp وضعیت‌ها، از last_play_at برای runaway_at و last_feed_at برای dead_at استفاده می‌کنیم.
    """
    now = _now()

    db = await open_db()
    try:
        runaway_hours = await _cfg_int(db, "runaway_recover_window_hours", 24)
        dead_archive_hours = await _cfg_int(db, "dead_archive_hours", 12)

        runaway_seconds = max(0, int(runaway_hours)) * 3600
        dead_seconds = max(0, int(dead_archive_hours)) * 3600

        # 1) پاکسازی runaway های قدیمی
        cur = await db.execute(
            """
            SELECT id, last_play_at
            FROM user_cats
            WHERE user_id=? AND status='runaway'
            """,
            (int(user_id),),
        )
        rows = await cur.fetchall()
        for r in rows:
            ts = int(r["last_play_at"] or 0)
            if runaway_seconds > 0 and ts > 0 and (now - ts) > runaway_seconds:
                await db.execute("DELETE FROM user_cats WHERE user_id=? AND id=?", (int(user_id), int(r["id"])))

        # 2) پاکسازی dead های قدیمی
        cur = await db.execute(
            """
            SELECT id, last_feed_at
            FROM user_cats
            WHERE user_id=? AND status='dead'
            """,
            (int(user_id),),
        )
        rows = await cur.fetchall()
        for r in rows:
            ts = int(r["last_feed_at"] or 0)
            if dead_seconds > 0 and ts > 0 and (now - ts) > dead_seconds:
                await db.execute("DELETE FROM user_cats WHERE user_id=? AND id=?", (int(user_id), int(r["id"])))

        # 3) بررسی active ها
        cur = await db.execute(
            """
            SELECT uc.id, uc.cat_id, uc.last_feed_at, uc.last_play_at, uc.obtained_at, cc.rarity
            FROM user_cats uc
            JOIN cats_catalog cc ON cc.cat_id = uc.cat_id
            WHERE uc.user_id=? AND uc.status='active'
            """,
            (int(user_id),),
        )
        active = await cur.fetchall()

        for r in active:
            rarity = str(r["rarity"] or "Common")
            obtained_at = int(r["obtained_at"] or now)

            last_feed = int(r["last_feed_at"] or obtained_at)
            last_play = int(r["last_play_at"] or obtained_at)

            # override از config (اختیاری)
            play_days = await _cfg_days(db, f"play_deadline_days_{rarity}", PLAY_DEADLINE_DAYS.get(rarity, 2))
            feed_days = await _cfg_days(db, f"feed_deadline_days_{rarity}", FEED_DEADLINE_DAYS.get(rarity, 2))

            play_limit = int(play_days) * 86400
            feed_limit = int(feed_days) * 86400

            # Divine: بی‌نهایت
            if play_days >= 10**8:
                play_limit = 10**18
            if feed_days >= 10**8:
                feed_limit = 10**18

            # مرگ اولویت بالاتر دارد
            if (now - last_feed) > feed_limit:
                await db.execute(
                    "UPDATE user_cats SET status='dead', last_feed_at=? WHERE user_id=? AND id=?",
                    (int(now), int(user_id), int(r["id"])),
                )
                await db.execute(
                    "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
                    (
                        int(user_id),
                        "cat_dead",
                        0,
                        json.dumps({"user_cat_id": int(r["id"]), "cat_id": int(r["cat_id"]), "rarity": rarity}, ensure_ascii=False),
                        int(now),
                    ),
                )
                continue

            if (now - last_play) > play_limit:
                await db.execute(
                    "UPDATE user_cats SET status='runaway', last_play_at=? WHERE user_id=? AND id=?",
                    (int(now), int(user_id), int(r["id"])),
                )
                await db.execute(
                    "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
                    (
                        int(user_id),
                        "cat_runaway",
                        0,
                        json.dumps({"user_cat_id": int(r["id"]), "cat_id": int(r["cat_id"]), "rarity": rarity}, ensure_ascii=False),
                        int(now),
                    ),
                )

        await db.commit()
    finally:
        await db.close()


async def feed_all(user_id: int) -> FeedPlayResult:
    now = _now()
    db = await open_db()
    try:
        cost_per_cat = await _cfg_int(db, "feed_cost_per_cat_mp", 1)

        cur = await db.execute(
            "SELECT COUNT(1) AS c FROM user_cats WHERE user_id=? AND status='active'",
            (int(user_id),),
        )
        r = await cur.fetchone()
        cnt = 0 if r is None else int(r["c"] or 0)

        total_cost = max(0, int(cost_per_cat)) * cnt

        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (int(user_id),))
        u = await cur.fetchone()
        mp = 0 if u is None else int(u["mp_balance"] or 0)

        if total_cost > 0 and mp < total_cost:
            return FeedPlayResult(False, "no_mp", 0, 0)

        if total_cost > 0:
            await db.execute("UPDATE users SET mp_balance = mp_balance - ? WHERE user_id=?", (int(total_cost), int(user_id)))

        await db.execute(
            "UPDATE user_cats SET last_feed_at=? WHERE user_id=? AND status='active'",
            (int(now), int(user_id)),
        )

        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (
                int(user_id),
                "feed_all",
                -int(total_cost),
                json.dumps({"count": int(cnt), "cost_per_cat": int(cost_per_cat)}, ensure_ascii=False),
                int(now),
            ),
        )

        await db.commit()
        return FeedPlayResult(True, mp_spent=int(total_cost), affected=int(cnt))
    finally:
        await db.close()


async def play_all(user_id: int) -> FeedPlayResult:
    now = _now()
    db = await open_db()
    try:
        cost_per_cat = await _cfg_int(db, "play_cost_per_cat_mp", 1)

        cur = await db.execute(
            "SELECT COUNT(1) AS c FROM user_cats WHERE user_id=? AND status='active'",
            (int(user_id),),
        )
        r = await cur.fetchone()
        cnt = 0 if r is None else int(r["c"] or 0)

        total_cost = max(0, int(cost_per_cat)) * cnt

        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (int(user_id),))
        u = await cur.fetchone()
        mp = 0 if u is None else int(u["mp_balance"] or 0)

        if total_cost > 0 and mp < total_cost:
            return FeedPlayResult(False, "no_mp", 0, 0)

        if total_cost > 0:
            await db.execute("UPDATE users SET mp_balance = mp_balance - ? WHERE user_id=?", (int(total_cost), int(user_id)))

        await db.execute(
            "UPDATE user_cats SET last_play_at=? WHERE user_id=? AND status='active'",
            (int(now), int(user_id)),
        )

        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (
                int(user_id),
                "play_all",
                -int(total_cost),
                json.dumps({"count": int(cnt), "cost_per_cat": int(cost_per_cat)}, ensure_ascii=False),
                int(now),
            ),
        )

        await db.commit()
        return FeedPlayResult(True, mp_spent=int(total_cost), affected=int(cnt))
    finally:
        await db.close()
