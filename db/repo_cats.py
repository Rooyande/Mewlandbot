# db/repo_cats.py
from __future__ import annotations

import time
from typing import Optional, Dict, Any, List

from db.db import session


def add_cat(
    owner_id: int,
    name: str,
    rarity: str,
    element: str,
    trait: str,
    description: str,
) -> int:
    now = int(time.time())
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cats (
                owner_id, name, rarity, element, trait, description,
                level, xp, hunger, happiness, gear,
                stat_power, stat_agility, stat_luck,
                created_at, last_tick_ts, alive, is_special
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, 100, 100, '',
                      1, 1, 1, ?, ?, 1, 0)
            """,
            (int(owner_id), name, rarity, element, trait, description, now, now),
        )
        return int(cur.lastrowid)


def list_user_cats(owner_id: int, include_dead: bool = False) -> List[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        if include_dead:
            cur.execute("SELECT * FROM cats WHERE owner_id = ? ORDER BY id", (int(owner_id),))
        else:
            cur.execute("SELECT * FROM cats WHERE owner_id = ? AND alive = 1 ORDER BY id", (int(owner_id),))
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def get_cat(cat_id: int, owner_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        if owner_id is None:
            cur.execute("SELECT * FROM cats WHERE id = ?", (int(cat_id),))
        else:
            cur.execute("SELECT * FROM cats WHERE id = ? AND owner_id = ?", (int(cat_id), int(owner_id)))
        row = cur.fetchone()
        return dict(row) if row else None


def update_cat_fields(cat_id: int, owner_id: Optional[int] = None, **fields: Any) -> None:
    # NOTE: این allowed باید با نیاز سرویس‌ها هم‌راستا باشد (rename/transfer/breed)
    allowed = {
        "hunger",
        "happiness",
        "xp",
        "level",
        "gear",
        "stat_power",
        "stat_agility",
        "stat_luck",
        "last_tick_ts",
        "alive",
        # لازم برای rename/transfer/breeding:
        "name",
        "owner_id",
        "last_breed_ts",
    }
    data = {k: v for k, v in fields.items() if k in allowed}
    if not data:
        return

    set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
    params = list(data.values())

    with session() as conn:
        cur = conn.cursor()
        if owner_id is None:
            params.append(int(cat_id))
            cur.execute(f"UPDATE cats SET {set_clause} WHERE id = ?", params)
        else:
            params.append(int(cat_id))
            params.append(int(owner_id))
            cur.execute(f"UPDATE cats SET {set_clause} WHERE id = ? AND owner_id = ?", params)


def kill_cat(cat_id: int, owner_id: Optional[int] = None) -> None:
    update_cat_fields(cat_id, owner_id, alive=0)
