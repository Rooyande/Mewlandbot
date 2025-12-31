# db/repo_users.py
import time
from typing import Optional, Dict, Any, List

from db.db import session


def get_user_by_tg(telegram_id: int) -> Optional[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_by_db_id(user_id: int) -> Optional[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_or_create_user(telegram_id: int, username: Optional[str]) -> int:
    with session() as conn:
        cur = conn.cursor()

        cur.execute("SELECT id, username FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cur.fetchone()
        if row:
            user_id = int(row["id"])
            old_username = row["username"]
            if username and username != old_username:
                cur.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
            return user_id

        cur.execute(
            "INSERT INTO users (telegram_id, username, created_at) VALUES (?, ?, ?)",
            (telegram_id, username, int(time.time())),
        )
        return int(cur.lastrowid)


def update_user_fields(telegram_id: int, **fields) -> None:
    allowed = {"mew_points", "last_mew_ts", "last_passive_ts", "username"}
    data = {k: v for k, v in fields.items() if k in allowed}
    if not data:
        return

    set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
    params = list(data.values()) + [telegram_id]

    with session() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE users SET {set_clause} WHERE telegram_id = ?", params)


def get_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT telegram_id, username, mew_points
            FROM users
            ORDER BY mew_points DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
