import json
import time
from dataclasses import dataclass
from zoneinfo import ZoneInfo
from datetime import datetime

from config import MEOW_REWARD, MEOW_COOLDOWN_SEC, MEOW_DAILY_LIMIT
from db import open_db

TZ = ZoneInfo("Europe/Amsterdam")


def _day_key(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, TZ)
    return dt.strftime("%Y%m%d")


@dataclass
class MeowResult:
    ok: bool
    reason: str = ""
    wait_sec: int = 0
    remaining_today: int = 0
    mp_balance: int = 0


async def _log(user_id: int, action: str, amount: int, meta: dict) -> None:
    db = await open_db()
    try:
        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (user_id, action, amount, json.dumps(meta, ensure_ascii=False), int(time.time())),
        )
        await db.commit()
    finally:
        await db.close()


async def meow_try(user_id: int) -> MeowResult:
    now = int(time.time())
    today = _day_key(now)

    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT window_key, count, last_ts FROM rate_limits WHERE user_id=? AND key='meow'",
            (user_id,),
        )
        row = await cur.fetchone()

        window_key = today
        count = 0
        last_ts = None

        if row:
            window_key = row["window_key"]
            count = int(row["count"] or 0)
            last_ts = row["last_ts"]

        if window_key != today:
            count = 0
            last_ts = None
            window_key = today

        if last_ts is not None:
            diff = now - int(last_ts)
            if diff < MEOW_COOLDOWN_SEC:
                wait_sec = MEOW_COOLDOWN_SEC - diff
                await _log(user_id, "meow_reject_cooldown", 0, {"wait_sec": wait_sec})
                return MeowResult(ok=False, reason="cooldown", wait_sec=wait_sec, remaining_today=max(0, MEOW_DAILY_LIMIT - count))

        if count >= MEOW_DAILY_LIMIT:
            await _log(user_id, "meow_reject_daily_limit", 0, {"limit": MEOW_DAILY_LIMIT})
            return MeowResult(ok=False, reason="daily_limit", remaining_today=0)

        count += 1
        last_ts = now

        await db.execute(
            "INSERT INTO rate_limits(user_id, key, window_key, count, last_ts) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET window_key=excluded.window_key, count=excluded.count, last_ts=excluded.last_ts",
            (user_id, "meow", window_key, count, last_ts),
        )

        await db.execute(
            "UPDATE users SET mp_balance = mp_balance + ? WHERE user_id=?",
            (MEOW_REWARD, user_id),
        )

        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (user_id,))
        u = await cur.fetchone()
        mp = 0 if u is None else int(u["mp_balance"] or 0)

        await db.commit()

        await _log(user_id, "meow", MEOW_REWARD, {"count_today": count, "limit": MEOW_DAILY_LIMIT})

        return MeowResult(ok=True, remaining_today=max(0, MEOW_DAILY_LIMIT - count), mp_balance=mp)
    finally:
        await db.close()
