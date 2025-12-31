import time
from typing import Any, Dict, List

from db.db import session


def add_achievement(user_id: int, achievement_id: str) -> bool:
    """
    True اگر واقعاً جدید اضافه شد، False اگر از قبل داشت.
    """
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO achievements (user_id, achievement_id, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, achievement_id, int(time.time())),
        )
        return cur.rowcount > 0


def has_achievement(user_id: int, achievement_id: str) -> bool:
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM achievements WHERE user_id = ? AND achievement_id = ?",
            (user_id, achievement_id),
        )
        return cur.fetchone() is not None


def list_user_achievements(user_id: int) -> List[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM achievements WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
