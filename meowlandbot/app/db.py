import aiosqlite
from typing import Optional, List

DB_PATH = "eclis_guard.db"


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path

    async def connect(self) -> aiosqlite.Connection:
        return await aiosqlite.connect(self.path)

    async def init(self) -> None:
        async with self.connect() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS safe_users (
                    user_id INTEGER PRIMARY KEY
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS banned_users (
                    user_id INTEGER,
                    group_id INTEGER,
                    PRIMARY KEY (user_id, group_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    group_id INTEGER PRIMARY KEY,
                    title TEXT
                )
            """)
            await db.commit()

    # ---------- SAFE USERS ----------

    async def is_safe(self, user_id: int) -> bool:
        async with self.connect() as db:
            cur = await db.execute(
                "SELECT 1 FROM safe_users WHERE user_id = ?",
                (user_id,)
            )
            return await cur.fetchone() is not None

    async def add_safe(self, user_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT OR IGNORE INTO safe_users (user_id) VALUES (?)",
                (user_id,)
            )
            await db.commit()

    # ---------- ADMINS ----------

    async def is_admin(self, user_id: int) -> bool:
        async with self.connect() as db:
            cur = await db.execute(
                "SELECT 1 FROM admins WHERE user_id = ?",
                (user_id,)
            )
            return await cur.fetchone() is not None

    async def add_admin(self, user_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
                (user_id,)
            )
            await db.commit()

    # ---------- BANS ----------

    async def add_ban(self, user_id: int, group_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT OR IGNORE INTO banned_users (user_id, group_id) VALUES (?, ?)",
                (user_id, group_id)
            )
            await db.commit()

    async def remove_ban(self, user_id: int, group_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "DELETE FROM banned_users WHERE user_id = ? AND group_id = ?",
                (user_id, group_id)
            )
            await db.commit()

    async def list_bans(self) -> List[tuple]:
        async with self.connect() as db:
            cur = await db.execute(
                "SELECT user_id, group_id FROM banned_users"
            )
            return await cur.fetchall()

    # ---------- GROUPS ----------

    async def add_group(self, group_id: int, title: Optional[str]) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT OR IGNORE INTO groups (group_id, title) VALUES (?, ?)",
                (group_id, title)
            )
            await db.commit()

    async def list_groups(self) -> List[tuple]:
        async with self.connect() as db:
            cur = await db.execute(
                "SELECT group_id, title FROM groups"
            )
            return await cur.fetchall()


db = Database()
