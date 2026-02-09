import json
import time
from typing import Dict

from db import open_db

DEFAULT_PASSIVE_CAP_HOURS = 24


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


async def _get_config_float(db, key: str, default: float) -> float:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return default
    try:
        return float(row["value"])
    except Exception:
        return default


async def _get_rarity_mult_cache(db) -> Dict[str, float]:
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


async def get_total_passive_rate(user_id: int) -> float:
    db = await open_db()
    try:
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

        level_bonus = await _get_config_float(db, "level_bonus", 0.0)
        rarity_mults = await _get_rarity_mult_cache(db)

        total_rate_per_hour = 0.0
        for r in rows:
            rarity = str(r["rarity"] or "").strip()
            base_rate = float(r["base_passive_rate"] or 0.0)  # MP/hour
            level = int(r["level"] or 1)

            rarity_mult = float(rarity_mults.get(rarity.lower(), 1.0))
            level_mult = 1.0 + (level_bonus * max(0, level - 1))
            item_mult = 1.0

            total_rate_per_hour += base_rate * rarity_mult * level_mult * item_mult

        return float(total_rate_per_hour)
    finally:
        await db.close()


async def apply_passive(user_id: int) -> int:
    now = int(time.time())

    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT last_passive_ts, passive_cap_hours FROM users WHERE user_id=?",
            (user_id,),
        )
        u = await cur.fetchone()
        if u is None:
            return 0

        last_ts = int(u["last_passive_ts"] or now)
        cap_hours = u["passive_cap_hours"]
        cap_hours = int(cap_hours) if cap_hours is not None else DEFAULT_PASSIVE_CAP_HOURS
        cap_sec = max(0, cap_hours) * 3600

        dt = now - last_ts
        if dt <= 0:
            return 0

        used = dt if cap_sec == 0 else min(dt, cap_sec)

        total_rate_per_hour = await get_total_passive_rate(user_id)
        rate_per_sec = total_rate_per_hour / 3600.0

        if rate_per_sec <= 0:
            await db.execute("UPDATE users SET last_passive_ts=? WHERE user_id=?", (now, user_id))
            await db.commit()
            return 0

        gen_float = used * rate_per_sec
        gen_int = int(gen_float)

        remainder = gen_float - gen_int
        remainder_sec = int(remainder / rate_per_sec) if remainder > 0 else 0
        new_last_ts = now - remainder_sec

        if gen_int > 0:
            await db.execute(
                "UPDATE users SET mp_balance = mp_balance + ?, last_passive_ts=? WHERE user_id=?",
                (gen_int, new_last_ts, user_id),
            )
        else:
            await db.execute(
                "UPDATE users SET last_passive_ts=? WHERE user_id=?",
                (new_last_ts, user_id),
            )

        await db.commit()

        if gen_int > 0:
            await _log(
                user_id,
                "passive_collect",
                gen_int,
                {"used_sec": used, "cap_hours": cap_hours, "rate_per_hour": total_rate_per_hour},
            )

        return gen_int
    finally:
        await db.close()
