from dataclasses import dataclass
from typing import Optional, List

from db import open_db


@dataclass
class ItemForSale:
    offer_id: int
    item_id: int
    name: str
    type: str
    price: int


@dataclass
class BuyItemResult:
    ok: bool
    reason: str | None = None
    name: str | None = None
    price: int | None = None


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


async def list_items_for_sale() -> List[ItemForSale]:
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT o.offer_id, o.item_id, o.price, c.name, c.type
            FROM item_shop_offers o
            JOIN items_catalog c ON c.item_id=o.item_id
            WHERE o.active=1 AND c.active=1
            ORDER BY o.offer_id DESC
            """
        )
        rows = await cur.fetchall()
        out: List[ItemForSale] = []
        for r in rows:
            out.append(
                ItemForSale(
                    offer_id=int(r["offer_id"]),
                    item_id=int(r["item_id"]),
                    name=str(r["name"]),
                    type=str(r["type"]),
                    price=int(r["price"]),
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
            SELECT o.offer_id, o.item_id, o.price, c.name, c.type
            FROM item_shop_offers o
            JOIN items_catalog c ON c.item_id=o.item_id
            WHERE o.active=1 AND c.active=1 AND o.item_id=?
            ORDER BY o.offer_id DESC
            LIMIT 1
            """,
            (int(item_id),),
        )
        r = await cur.fetchone()
        if r is None:
            return None
        return ItemForSale(
            offer_id=int(r["offer_id"]),
            item_id=int(r["item_id"]),
            name=str(r["name"]),
            type=str(r["type"]),
            price=int(r["price"]),
        )
    finally:
        await db.close()


async def _weekly_cap_ok(user_id: int, cap: int) -> bool:
    if cap <= 0:
        return True
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT COUNT(1) AS c
            FROM economy_logs
            WHERE user_id=? AND action='buy_item' AND ts >= (strftime('%s','now') - 7*24*3600)
            """,
            (int(user_id),),
        )
        r = await cur.fetchone()
        used = int(r["c"]) if r else 0
        return used < cap
    finally:
        await db.close()


async def buy_item(user_id: int, item_id: int, qty: int = 1) -> BuyItemResult:
    if qty <= 0:
        qty = 1

    offer = await get_item_for_sale(int(item_id))
    if offer is None:
        return BuyItemResult(ok=False, reason="not_found")

    cap = await _cfg_int("item_shop_weekly_cap", 0)
    if not await _weekly_cap_ok(user_id, cap):
        return BuyItemResult(ok=False, reason="weekly_cap")

    total_price = int(offer.price) * int(qty)

    db = await open_db()
    try:
        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (int(user_id),))
        u = await cur.fetchone()
        if u is None:
            return BuyItemResult(ok=False, reason="not_found")

        mp = int(u["mp_balance"])
        if mp < total_price:
            return BuyItemResult(ok=False, reason="no_mp")

        await db.execute("UPDATE users SET mp_balance=mp_balance-? WHERE user_id=?", (total_price, int(user_id)))

        await db.execute(
            """
            INSERT INTO user_items(user_id, item_id, qty, durability_state_json)
            VALUES(?,?,?,?)
            ON CONFLICT(user_id, item_id) DO UPDATE SET qty = qty + excluded.qty
            """,
            (int(user_id), int(offer.item_id), int(qty), "{}"),
        )

        await db.execute(
            """
            INSERT INTO economy_logs(user_id, action, amount, meta_json, ts)
            VALUES(?,?,?,?,strftime('%s','now'))
            """,
            (
                int(user_id),
                "buy_item",
                -int(total_price),
                f'{{"item_id":{int(offer.item_id)},"qty":{int(qty)},"price":{int(offer.price)}}}',
            ),
        )

        await db.commit()
        return BuyItemResult(ok=True, name=offer.name, price=int(total_price))
    finally:
        await db.close()
