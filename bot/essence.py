import time
from dataclasses import dataclass
from typing import Optional

from db import open_db


def _now() -> int:
    return int(time.time())


@dataclass
class EssenceResult:
    ok: bool
    reason: str = ""
    essence: int | None = None


async def get_essence(user_id: int) -> int:
    db = await open_db()
    try:
        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return 0 if row is None else int(row["essence"] or 0)
    finally:
        await db.close()


async def add_essence(user_id: int, amount: int, reason: str = "", meta_json: str = "{}") -> EssenceResult:
    if amount <= 0:
        return EssenceResult(False, "invalid_amount")

    ts = _now()
    db = await open_db()
    try:
        await db.execute("INSERT OR IGNORE INTO resources(user_id, essence) VALUES(?, 0)", (user_id,))
        await db.execute(
            "UPDATE resources SET essence = essence + ? WHERE user_id=?",
            (int(amount), int(user_id)),
        )
        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (int(user_id), reason or "essence_add", int(amount), meta_json, ts),
        )
        await db.commit()

        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return EssenceResult(True, essence=0 if row is None else int(row["essence"] or 0))
    finally:
        await db.close()


async def spend_essence(user_id: int, amount: int, reason: str = "", meta_json: str = "{}") -> EssenceResult:
    if amount <= 0:
        return EssenceResult(False, "invalid_amount")

    ts = _now()
    db = await open_db()
    try:
        await db.execute("INSERT OR IGNORE INTO resources(user_id, essence) VALUES(?, 0)", (user_id,))

        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        have = 0 if row is None else int(row["essence"] or 0)
        if have < amount:
            return EssenceResult(False, "no_essence", essence=have)

        await db.execute(
            "UPDATE resources SET essence = essence - ? WHERE user_id=?",
            (int(amount), int(user_id)),
        )
        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (int(user_id), reason or "essence_spend", -int(amount), meta_json, ts),
        )
        await db.commit()

        return EssenceResult(True, essence=have - int(amount))
    finally:
        await db.close()
