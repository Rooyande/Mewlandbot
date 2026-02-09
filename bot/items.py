from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from db import open_db


@dataclass
class UserItemRow:
    item_id: int
    name: str
    type: str
    qty: int
    tradable: int
    active: int


async def list_user_items(user_id: int) -> List[UserItemRow]:
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT
              ic.item_id,
              ic.name,
              ic.type,
              ui.qty,
              COALESCE(ic.tradable, 0) AS tradable,
              COALESCE(ic.active, 1) AS active
            FROM user_items ui
            JOIN items_catalog ic ON ic.item_id = ui.item_id
            WHERE ui.user_id=?
              AND ui.qty > 0
              AND COALESCE(ic.active, 1)=1
            ORDER BY ic.type ASC, ic.name ASC
            """,
            (user_id,),
        )
        rows = await cur.fetchall()
        out: List[UserItemRow] = []
        for r in rows:
            out.append(
                UserItemRow(
                    item_id=int(r["item_id"]),
                    name=str(r["name"]),
                    type=str(r["type"] or ""),
                    qty=int(r["qty"] or 0),
                    tradable=int(r["tradable"] or 0),
                    active=int(r["active"] or 1),
                )
            )
        return out
    finally:
        await db.close()


async def get_item_basic(item_id: int) -> Optional[Dict[str, Any]]:
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT item_id, name, type, effect_json, durability_rules_json, tradable, active
            FROM items_catalog
            WHERE item_id=?
            """,
            (item_id,),
        )
        r = await cur.fetchone()
        if r is None:
            return None
        return {
            "item_id": int(r["item_id"]),
            "name": str(r["name"]),
            "type": str(r["type"] or ""),
            "effect_json": str(r["effect_json"] or ""),
            "durability_rules_json": str(r["durability_rules_json"] or ""),
            "tradable": int(r["tradable"] or 0),
            "active": int(r["active"] or 1),
        }
    finally:
        await db.close()


async def user_item_qty(user_id: int, item_id: int) -> int:
    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT qty FROM user_items WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        )
        r = await cur.fetchone()
        return 0 if r is None else int(r["qty"] or 0)
    finally:
        await db.close()
