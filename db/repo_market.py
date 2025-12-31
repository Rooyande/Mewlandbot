import time
from typing import Any, Dict, List, Optional

from db.db import session

MARKET_FEE_PERCENT = 5
MARKET_LISTING_DURATION = 7 * 24 * 3600  # 7 days


def _cleanup_expired(cur) -> None:
    now = int(time.time())
    cur.execute(
        "UPDATE market_listings SET active = 0 WHERE active = 1 AND expires_at < ?",
        (now,),
    )


def create_listing(seller_id: int, cat_id: int, price: int) -> Optional[int]:
    now = int(time.time())
    expires_at = now + MARKET_LISTING_DURATION

    with session() as conn:
        cur = conn.cursor()

        # cat must be owned by seller + alive
        cur.execute("SELECT owner_id, alive FROM cats WHERE id = ?", (cat_id,))
        row = cur.fetchone()
        if not row or int(row["owner_id"]) != int(seller_id) or int(row["alive"]) != 1:
            return None

        # already listed?
        cur.execute(
            "SELECT id FROM market_listings WHERE cat_id = ? AND active = 1",
            (cat_id,),
        )
        if cur.fetchone():
            return None

        cur.execute(
            """
            INSERT INTO market_listings (cat_id, seller_id, price, created_at, expires_at, active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (cat_id, seller_id, price, now, expires_at),
        )
        return int(cur.lastrowid)


def list_active() -> List[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        _cleanup_expired(cur)
        cur.execute(
            """
            SELECT * FROM market_listings
            WHERE active = 1
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def list_mine(user_id: int) -> List[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        _cleanup_expired(cur)
        cur.execute(
            """
            SELECT * FROM market_listings
            WHERE active = 1 AND seller_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def cancel_listing(listing_id: int, user_id: int) -> bool:
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE market_listings
            SET active = 0
            WHERE id = ? AND seller_id = ? AND active = 1
            """,
            (listing_id, user_id),
        )
        return cur.rowcount > 0


def buy_listing(listing_id: int, buyer_id: int) -> Optional[Dict[str, Any]]:
    """
    atomic-ish خرید:
    - چک آگهی
    - چک موجودی خریدار
    - انتقال مالکیت گربه
    - انتقال پول (fee کم می‌شود)
    - deactivate listing
    """
    with session() as conn:
        conn.isolation_level = "EXCLUSIVE"
        cur = conn.cursor()

        _cleanup_expired(cur)
        now = int(time.time())

        cur.execute(
            """
            SELECT * FROM market_listings
            WHERE id = ? AND active = 1 AND expires_at >= ?
            """,
            (listing_id, now),
        )
        listing = cur.fetchone()
        if not listing:
            return None

        listing = dict(listing)
        price = int(listing["price"])
        cat_id = int(listing["cat_id"])
        seller_id = int(listing["seller_id"])

        if buyer_id == seller_id:
            return None

        cur.execute("SELECT mew_points FROM users WHERE id = ?", (buyer_id,))
        buyer = cur.fetchone()
        if not buyer or int(buyer["mew_points"]) < price:
            return None

        fee = int(price * MARKET_FEE_PERCENT / 100)
        net = price - fee

        # balances
        cur.execute("UPDATE users SET mew_points = mew_points - ? WHERE id = ?", (price, buyer_id))
        cur.execute("UPDATE users SET mew_points = mew_points + ? WHERE id = ?", (net, seller_id))

        # cat owner
        cur.execute("UPDATE cats SET owner_id = ? WHERE id = ?", (buyer_id, cat_id))

        # deactivate listing
        cur.execute("UPDATE market_listings SET active = 0 WHERE id = ?", (listing_id,))

        return {
            "listing_id": listing_id,
            "cat_id": cat_id,
            "price": price,
            "seller_id": seller_id,
            "buyer_id": buyer_id,
            "fee": fee,
            "net_amount": net,
        }
