import json
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from db import open_db

DEFAULT_ITEM_PRICE = 100
DEFAULT_WEEKLY_CAP = 50


def _now() -> int:
    return int(time.time())


async def _week_key(now_ts: int) -> str:
    import datetime as _dt

    dt = _dt.datetime.utcfromtimestamp(now_ts)
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w}"


async def _cfg_int(db, key: str, default: int) -> int:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return default
    try:
        return int(row["value"])
    except Exception:
        return default


async def _item_price(db, item_id: int) -> int:
    return await _cfg_int(db, f"item_price_{item_id}", DEFAULT_ITEM_PRICE)


async def _weekly_item_buys(db, user_id: int, wk: str) -> int:
    cur = await db.execute(
        """
        SELECT COUNT(1) AS c
        FROM economy_logs
        WHERE user_id=?
          AND action='item_buy'
          AND meta_json LIKE ?
        """,
        (user_id, f'%\"week\":\"{wk}\"%'),
    )
    r = await cur.fetchone()
    return 0 if r is None else int(r["c"] or 0)


@dataclass
class ItemForSale:
    item_id: int
    name: str
    type: str
    price: int


@dataclass
class BuyItemResult:
    ok: bool
    reason: str = ""
    item_id: int | None = None
    name: str | None = None
    qty: int = 0
    price: int = 0


async def list_items_for_sale() -> List[ItemForSale]:
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT item_id, name, type
            FROM items_catalog
            WHERE COALESCE(active, 1)=1
            ORDER BY type ASC, name ASC
            """
        )
        rows = await cur.fetchall()
        out: List[ItemForSale] = []
        for r in rows:
            item_id = int(r["item_id"])
            price = await _item_price(db, item_id)
            out.append(
                ItemForSale(
                    item_id=item_id,
                    name=str(r["name"]),
                    type=str(r["type"] or ""),
                    price=int(price),
                )
            )
        return out
    finally:
        await db.close()


async def get_item_for_sale(item_id: int) -> Optional[ItemForSale]:
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT item_id, name, type
            FROM items_catalog
            WHERE item_id=? AND COALESCE(active, 1)=1
            """,
            (item_id,),
        )
        r = await cur.fetchone()
        if r is None:
            return None
        price = await _item_price(db, int(r["item_id"]))
        return ItemForSale(
            item_id=int(r["item_id"]),
            name=str(r["name"]),
            type=str(r["type"] or ""),
            price=int(price),
        )
    finally:
        await db.close()


async def buy_item(user_id: int, item_id: int, qty: int = 1) -> BuyItemResult:
    qty = int(qty)
    if qty <= 0:
        return BuyItemResult(False, "bad_qty")

    now = _now()
    wk = await _week_key(now)

    db = await open_db()
    try:
        cap = await _cfg_int(db, "item_weekly_cap", DEFAULT_WEEKLY_CAP)
        used = await _weekly_item_buys(db, user_id, wk)
        if used >= cap:
            return BuyItemResult(False, "weekly_cap")

        it = await get_item_for_sale(item_id)
        if it is None:
            return BuyItemResult(False, "not_found")

        price_each = int(it.price)
        total_price = price_each * qty

        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (user_id,))
        u = await cur.fetchone()
        mp = 0 if u is None else int(u["mp_balance"] or 0)
        if mp < total_price:
            return BuyItemResult(False, "no_mp")

        await db.execute("UPDATE users SET mp_balance = mp_balance - ? WHERE user_id=?", (total_price, user_id))

        await db.execute(
            """
            INSERT INTO user_items(user_id, item_id, qty)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id, item_id) DO UPDATE SET qty = qty + excluded.qty
            """,
            (user_id, item_id, qty),
        )

        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (
                user_id,
                "item_buy",
                -int(total_price),
                json.dumps({"item_id": int(item_id), "qty": int(qty), "week": wk}, ensure_ascii=False),
                now,
            ),
        )

        await db.commit()

        return BuyItemResult(
            True,
            item_id=int(item_id),
            name=str(it.name),
            qty=int(qty),
            price=int(total_price),
        )
    finally:
        await db.close()
