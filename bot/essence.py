import json
import time
from dataclasses import dataclass
from typing import Optional

from db import open_db


def _now() -> int:
    return int(time.time())


async def _ensure(user_id: int) -> None:
    db = await open_db()
    try:
        await db.execute("INSERT OR IGNORE INTO resources(user_id, essence) VALUES(?, 0)", (int(user_id),))
        await db.commit()
    finally:
        await db.close()


async def get_essence(user_id: int) -> int:
    await _ensure(user_id)
    db = await open_db()
    try:
        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (int(user_id),))
        r = await cur.fetchone()
        return 0 if r is None else int(r["essence"] or 0)
    finally:
        await db.close()


@dataclass
class EssenceOpResult:
    ok: bool
    reason: str = ""
    new_balance: int = 0


async def add_essence(user_id: int, amount: int, reason: str = "add_essence", meta: dict | None = None) -> EssenceOpResult:
    amt = max(0, int(amount))
    ts = _now()
    await _ensure(user_id)

    db = await open_db()
    try:
        await db.execute("UPDATE resources SET essence = essence + ? WHERE user_id=?", (amt, int(user_id)))
        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (int(user_id), reason, int(amt), json.dumps(meta or {}, ensure_ascii=False), int(ts)),
        )
        await db.commit()

        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (int(user_id),))
        r = await cur.fetchone()
        bal = 0 if r is None else int(r["essence"] or 0)
        return EssenceOpResult(True, new_balance=bal)
    finally:
        await db.close()


async def spend_essence(user_id: int, amount: int, reason: str = "spend_essence", meta: dict | None = None) -> EssenceOpResult:
    amt = max(0, int(amount))
    ts = _now()
    await _ensure(user_id)

    db = await open_db()
    try:
        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (int(user_id),))
        r = await cur.fetchone()
        bal = 0 if r is None else int(r["essence"] or 0)

        if bal < amt:
            return EssenceOpResult(False, "no_essence", new_balance=bal)

        await db.execute("UPDATE resources SET essence = essence - ? WHERE user_id=?", (amt, int(user_id)))
        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (int(user_id), reason, -int(amt), json.dumps(meta or {}, ensure_ascii=False), int(ts)),
        )
        await db.commit()

        cur2 = await db.execute("SELECT essence FROM resources WHERE user_id=?", (int(user_id),))
        r2 = await cur2.fetchone()
        bal2 = 0 if r2 is None else int(r2["essence"] or 0)
        return EssenceOpResult(True, new_balance=bal2)
    finally:
        await db.close()
