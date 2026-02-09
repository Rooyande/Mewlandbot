import time
from typing import Dict, Tuple, List

from db import open_db

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

RUNAWAY_RECOVER_WINDOW_SEC = 24 * 3600


def _now() -> int:
    return int(time.time())


async def _active_cats(db, user_id: int):
    cur = await db.execute(
        """
        SELECT uc.id, uc.last_feed_at, uc.last_play_at, cc.rarity
        FROM user_cats uc
        JOIN cats_catalog cc ON cc.cat_id = uc.cat_id
        WHERE uc.user_id=? AND uc.status='active'
        """,
        (user_id,),
    )
    return await cur.fetchall()


def _due(last_ts: int | None, deadline_days: int, now: int) -> int:
    if last_ts is None:
        return 0
    return int(last_ts) + int(deadline_days * 86400)


async def apply_survival(user_id: int) -> Tuple[int, int]:
    now = _now()
    db = await open_db()
    try:
        rows = await _active_cats(db, user_id)

        runaway_ids: List[int] = []
        dead_ids: List[int] = []

        for r in rows:
            uc_id = int(r["id"])
            rarity = str(r["rarity"] or "").lower()
            fd = FEED_DEADLINE_DAYS.get(rarity, 2)
            pd = PLAY_DEADLINE_DAYS.get(rarity, 2)

            feed_due = _due(r["last_feed_at"], fd, now)
            play_due = _due(r["last_play_at"], pd, now)

            if feed_due <= now:
                dead_ids.append(uc_id)
                continue
            if play_due <= now:
                runaway_ids.append(uc_id)
                continue

        if runaway_ids:
            q = ",".join("?" for _ in runaway_ids)
            await db.execute(
                f"UPDATE user_cats SET status='runaway' WHERE user_id=? AND id IN ({q})",
                (user_id, *runaway_ids),
            )

        if dead_ids:
            q = ",".join("?" for _ in dead_ids)
            await db.execute(
                f"UPDATE user_cats SET status='dead' WHERE user_id=? AND id IN ({q})",
                (user_id, *dead_ids),
            )

        await db.commit()
        return len(runaway_ids), len(dead_ids)
    finally:
        await db.close()


async def cleanup_runaways() -> int:
    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT id FROM user_cats
            WHERE status='runaway'
              AND obtained_at IS NOT NULL
              AND (? - obtained_at) > ?
            """,
            (now, RUNAWAY_RECOVER_WINDOW_SEC),
        )
        rows = await cur.fetchall()
        ids = [int(r["id"]) for r in rows]
        if not ids:
            return 0

        q = ",".join("?" for _ in ids)
        await db.execute(f"DELETE FROM user_cats WHERE id IN ({q})", (*ids,))
        await db.commit()
        return len(ids)
    finally:
        await db.close()


async def feed_all(user_id: int) -> int:
    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            "UPDATE user_cats SET last_feed_at=? WHERE user_id=? AND status='active'",
            (now, user_id),
        )
        await db.commit()
        return cur.rowcount or 0
    finally:
        await db.close()


async def play_all(user_id: int) -> int:
    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            "UPDATE user_cats SET last_play_at=? WHERE user_id=? AND status='active'",
            (now, user_id),
        )
        await db.commit()
        return cur.rowcount or 0
    finally:
        await db.close()
