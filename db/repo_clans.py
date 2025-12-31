import time
from typing import Any, Dict, List, Optional

from db.db import session

CLAN_MAX_MEMBERS = 50
CLAN_CREATION_COST = 5000
CLAN_BONUS_PER_MEMBER = 0.02  # 2%


def create_clan(leader_id: int, name: str) -> bool:
    with session() as conn:
        cur = conn.cursor()

        # user already in clan?
        cur.execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (leader_id,))
        if cur.fetchone():
            return False

        # create
        cur.execute(
            "INSERT INTO clans (name, leader_id, created_at) VALUES (?, ?, ?)",
            (name, leader_id, int(time.time())),
        )
        clan_id = int(cur.lastrowid)

        cur.execute(
            "INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?)",
            (clan_id, leader_id, int(time.time())),
        )
        return True


def get_user_clan(user_id: int) -> Optional[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.id, c.name, c.leader_id, c.created_at, u.username AS leader_username
            FROM clan_members m
            JOIN clans c ON m.clan_id = c.id
            LEFT JOIN users u ON c.leader_id = u.id
            WHERE m.user_id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_clan_by_name(name: str) -> Optional[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.id, c.name, c.leader_id, c.created_at, u.username AS leader_username
            FROM clans c
            LEFT JOIN users u ON c.leader_id = u.id
            WHERE c.name = ?
            """,
            (name,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_members(clan_id: int) -> List[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.id AS user_id, u.username, u.telegram_id, u.mew_points
            FROM clan_members m
            JOIN users u ON m.user_id = u.id
            WHERE m.clan_id = ?
            ORDER BY u.mew_points DESC
            """,
            (clan_id,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def join_clan(user_id: int, clan_name: str) -> bool:
    with session() as conn:
        cur = conn.cursor()

        # already in clan?
        cur.execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            return False

        cur.execute("SELECT id FROM clans WHERE name = ?", (clan_name,))
        row = cur.fetchone()
        if not row:
            return False
        clan_id = int(row["id"])

        # capacity
        cur.execute("SELECT COUNT(*) AS cnt FROM clan_members WHERE clan_id = ?", (clan_id,))
        cnt = int(cur.fetchone()["cnt"])
        if cnt >= CLAN_MAX_MEMBERS:
            return False

        cur.execute(
            "INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?)",
            (clan_id, user_id, int(time.time())),
        )
        return True


def leave_clan(user_id: int) -> Optional[Dict[str, Any]]:
    """
    خروجی:
    - None اگر عضو نبود
    - dict: { "was_leader": bool, "clan_id": int, "clan_name": str }
    """
    with session() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT c.id AS clan_id, c.name AS clan_name, c.leader_id
            FROM clan_members m
            JOIN clans c ON m.clan_id = c.id
            WHERE m.user_id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        clan_id = int(row["clan_id"])
        clan_name = str(row["clan_name"])
        was_leader = int(row["leader_id"]) == int(user_id)

        # remove membership
        cur.execute("DELETE FROM clan_members WHERE clan_id = ? AND user_id = ?", (clan_id, user_id))

        return {"was_leader": was_leader, "clan_id": clan_id, "clan_name": clan_name}


def delete_clan(clan_id: int) -> bool:
    with session() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM clan_members WHERE clan_id = ?", (clan_id,))
        cur.execute("DELETE FROM clans WHERE id = ?", (clan_id,))
        return cur.rowcount > 0


def list_available() -> List[Dict[str, Any]]:
    with session() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.id, c.name, c.leader_id, c.created_at,
                   u.username AS leader_username,
                   COUNT(m.user_id) AS member_count
            FROM clans c
            LEFT JOIN clan_members m ON c.id = m.clan_id
            LEFT JOIN users u ON c.leader_id = u.id
            GROUP BY c.id, c.name, c.leader_id, c.created_at, u.username
            ORDER BY member_count DESC, c.created_at ASC
            """
        )
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            if int(d.get("member_count") or 0) < CLAN_MAX_MEMBERS:
                out.append(d)
        return out


def calc_bonus(member_count: int) -> float:
    return 1.0 + (member_count * CLAN_BONUS_PER_MEMBER)
