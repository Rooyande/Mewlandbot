# db.py
import os
import sqlite3
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ========= CONFIG =========

DB_PATH = os.getenv("DB_PATH", os.getenv("DATABASE_URL", "mewland.db"))

# These are duplicated from your main code so DB-level logic can work
CLAN_MAX_MEMBERS = 50
MARKET_FEE_PERCENT = 5  # must stay in sync with main.py


# ========= LOW LEVEL HELPERS =========

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row) if row is not None else {}


# ========= SCHEMA INIT / MAINTENANCE =========

def init_db():
    """Create all tables if they don't exist."""
    conn = _get_conn()
    cur = conn.cursor()

    # users
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id     INTEGER UNIQUE NOT NULL,
            username        TEXT,
            mew_points      INTEGER DEFAULT 0,
            last_mew_ts     INTEGER DEFAULT 0,
            last_passive_ts INTEGER DEFAULT 0,
            created_at      INTEGER DEFAULT (strftime('%s','now'))
        );
        """
    )

    # user_groups: where players have used bot in which chat
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_groups (
            user_id  INTEGER NOT NULL,
            chat_id  INTEGER NOT NULL,
            joined_at INTEGER DEFAULT (strftime('%s','now')),
            PRIMARY KEY (user_id, chat_id)
        );
        """
    )

    # cats
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cats (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id        INTEGER,
            name            TEXT,
            rarity          TEXT,
            element         TEXT,
            trait           TEXT,
            description     TEXT,
            level           INTEGER DEFAULT 1,
            xp              INTEGER DEFAULT 0,
            hunger          INTEGER DEFAULT 100,
            happiness       INTEGER DEFAULT 100,
            gear            TEXT,
            stat_power      INTEGER DEFAULT 1,
            stat_agility    INTEGER DEFAULT 1,
            stat_luck       INTEGER DEFAULT 1,
            created_at      INTEGER DEFAULT (strftime('%s','now')),
            last_tick_ts    INTEGER DEFAULT 0,
            alive           INTEGER DEFAULT 1,
            last_breed_ts   INTEGER DEFAULT 0,
            is_special      INTEGER DEFAULT 0,
            special_ability TEXT
        );
        """
    )

    # achievements per user
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS achievements (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            achievement_id TEXT NOT NULL,
            created_at     INTEGER DEFAULT (strftime('%s','now')),
            UNIQUE (user_id, achievement_id)
        );
        """
    )

    # clans
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clans (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            leader_id  INTEGER NOT NULL,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        """
    )

    # clan members
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clan_members (
            clan_id   INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            joined_at INTEGER DEFAULT (strftime('%s','now')),
            PRIMARY KEY (clan_id, user_id)
        );
        """
    )

    # market listings
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS market_listings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            cat_id     INTEGER NOT NULL UNIQUE,
            seller_id  INTEGER NOT NULL,
            price      INTEGER NOT NULL,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            expires_at INTEGER NOT NULL,
            active     INTEGER DEFAULT 1
        );
        """
    )

    # breeding history
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cat_breeding (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            parent1_id  INTEGER NOT NULL,
            parent2_id  INTEGER NOT NULL,
            child_id    INTEGER,
            success     INTEGER NOT NULL,
            created_at  INTEGER DEFAULT (strftime('%s','now'))
        );
        """
    )

    # daily group event counters
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_events (
            chat_id INTEGER NOT NULL,
            date    TEXT NOT NULL,
            count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, date)
        );
        """
    )

    # active events in groups
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS active_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id         INTEGER NOT NULL,
            event_id        TEXT NOT NULL,
            text            TEXT NOT NULL,
            expected_answer TEXT NOT NULL,
            created_at      INTEGER DEFAULT (strftime('%s','now'))
        );
        """
    )

    # some indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_mew_points ON users(mew_points DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cats_owner ON cats(owner_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_market_active ON market_listings(active, expires_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_clan_members_clan ON clan_members(clan_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_active_events_chat ON active_events(chat_id);")

    conn.commit()
    conn.close()


def update_daily_events_table():
    """Housekeeping for daily_events & active_events (optional cleanup)."""
    conn = _get_conn()
    cur = conn.cursor()

    # drop very old daily event rows (older than 60 days)
    try:
        cutoff_ts = int(time.time()) - 60 * 24 * 3600
        cutoff_date = time.strftime("%Y-%m-%d", time.gmtime(cutoff_ts))
        cur.execute("DELETE FROM daily_events WHERE date < ?", (cutoff_date,))
    except Exception as e:
        logger.error(f"Error cleaning daily_events: {e}")

    # delete active_events older than 48 hours (they can't be valid)
    try:
        cutoff_ts = int(time.time()) - 48 * 3600
        cur.execute("DELETE FROM active_events WHERE created_at < ?", (cutoff_ts,))
    except Exception as e:
        logger.error(f"Error cleaning active_events: {e}")

    conn.commit()
    conn.close()


# ========= USER FUNCTIONS =========

def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_db_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_or_create_user(telegram_id: int, username: Optional[str]) -> Optional[int]:
    """Return internal user id; create user if needed."""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, username FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cur.fetchone()

    if row:
        user_id = row["id"]
        old_username = row["username"]
        # update username if changed
        if username and username != old_username:
            cur.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
            conn.commit()
        conn.close()
        return user_id

    # create user
    try:
        cur.execute(
            "INSERT INTO users (telegram_id, username, created_at) VALUES (?, ?, ?)",
            (telegram_id, username, int(time.time())),
        )
        conn.commit()
        user_id = cur.lastrowid
    except Exception as e:
        logger.error(f"Error creating user {telegram_id}: {e}")
        conn.close()
        return None

    conn.close()
    return user_id


def update_user_mew(telegram_id: int, **kwargs):
    """Update mew-related fields: mew_points, last_mew_ts, last_passive_ts."""
    if not kwargs:
        return

    allowed = {"mew_points", "last_mew_ts", "last_passive_ts"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return

    set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
    params = list(fields.values())
    params.append(telegram_id)

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(f"UPDATE users SET {set_clause} WHERE telegram_id = ?", params)
    conn.commit()
    conn.close()


def register_user_group(user_id: int, chat_id: int):
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT OR IGNORE INTO user_groups (user_id, chat_id, joined_at) VALUES (?, ?, ?)",
            (user_id, chat_id, int(time.time())),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error registering user group: {e}")
    finally:
        conn.close()


def get_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT username, telegram_id, mew_points
        FROM users
        ORDER BY mew_points DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_users() -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ========= CAT FUNCTIONS =========

def add_cat(
    owner_id: int,
    name: str,
    rarity: str,
    element: str,
    trait: str,
    description: str,
) -> Optional[int]:
    now = int(time.time())
    conn = _get_conn()
    cur = conn.cursor()
    try:
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
            (owner_id, name, rarity, element, trait, description, now, now),
        )
        conn.commit()
        cat_id = cur.lastrowid
    except Exception as e:
        logger.error(f"Error adding cat: {e}")
        cat_id = None
    finally:
        conn.close()

    return cat_id


def add_special_cat(
    owner_id: int,
    name: str,
    rarity: str,
    element: str,
    trait: str,
    description: str,
    special_ability: Optional[str] = None,
) -> Optional[int]:
    now = int(time.time())
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO cats (
                owner_id, name, rarity, element, trait, description,
                level, xp, hunger, happiness, gear,
                stat_power, stat_agility, stat_luck,
                created_at, last_tick_ts, alive,
                is_special, special_ability
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, 100, 100, '',
                      1, 1, 1, ?, ?, 1, 1, ?)
            """,
            (owner_id, name, rarity, element, trait, description, now, now, special_ability),
        )
        conn.commit()
        cat_id = cur.lastrowid
    except Exception as e:
        logger.error(f"Error adding special cat: {e}")
        cat_id = None
    finally:
        conn.close()
    return cat_id


def get_user_cats(owner_id: int, include_dead: bool = True) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    if include_dead:
        cur.execute("SELECT * FROM cats WHERE owner_id = ? ORDER BY id", (owner_id,))
    else:
        cur.execute(
            "SELECT * FROM cats WHERE owner_id = ? AND alive = 1 ORDER BY id", (owner_id,)
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cat(cat_id: int, owner_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()

    if owner_id is None:
        cur.execute("SELECT * FROM cats WHERE id = ?", (cat_id,))
    else:
        cur.execute("SELECT * FROM cats WHERE id = ? AND owner_id = ?", (cat_id, owner_id))

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_cat_stats(cat_id: int, owner_id: Optional[int] = None, **kwargs):
    """Update arbitrary fields on a cat (hunger, happiness, xp, level, gear, last_tick_ts, last_breed_ts...)."""
    if not kwargs:
        return

    allowed_fields = {
        "hunger",
        "happiness",
        "xp",
        "level",
        "gear",
        "stat_power",
        "stat_agility",
        "stat_luck",
        "last_tick_ts",
        "last_breed_ts",
        "alive",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not fields:
        return

    set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
    params = list(fields.values())
    params.append(cat_id)

    conn = _get_conn()
    cur = conn.cursor()

    if owner_id is not None:
        params.append(owner_id)
        query = f"UPDATE cats SET {set_clause} WHERE id = ? AND owner_id = ?"
    else:
        query = f"UPDATE cats SET {set_clause} WHERE id = ?"

    cur.execute(query, params)
    conn.commit()
    conn.close()


def kill_cat(cat_id: int, owner_id: Optional[int] = None):
    """Mark cat as dead (alive=0)."""
    update_cat_stats(cat_id, owner_id, alive=0)


def rename_cat(owner_id: int, cat_id: int, new_name: str) -> bool:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE cats SET name = ? WHERE id = ? AND owner_id = ?",
        (new_name, cat_id, owner_id),
    )
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def set_cat_owner(cat_id: int, new_owner_id: int) -> bool:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE cats SET owner_id = ? WHERE id = ?", (new_owner_id, cat_id))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


# ========= ACHIEVEMENTS =========

def add_achievement(user_id: int, achievement_id: str):
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT OR IGNORE INTO achievements (user_id, achievement_id, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, achievement_id, int(time.time())),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error adding achievement: {e}")
    finally:
        conn.close()


def get_user_achievements(user_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM achievements WHERE user_id = ? ORDER BY created_at", (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ========= CLANS =========

def create_clan(leader_user_id: int, clan_name: str, cost: int) -> bool:
    """Create clan and add leader as member. Cost handled in main code, not here."""
    conn = _get_conn()
    cur = conn.cursor()
    try:
        # ensure user not already in clan
        cur.execute(
            """
            SELECT c.id
            FROM clans c
            JOIN clan_members m ON m.clan_id = c.id
            WHERE m.user_id = ?
            """,
            (leader_user_id,),
        )
        if cur.fetchone():
            conn.close()
            return False

        cur.execute(
            "INSERT INTO clans (name, leader_id, created_at) VALUES (?, ?, ?)",
            (clan_name, leader_user_id, int(time.time())),
        )
        clan_id = cur.lastrowid

        cur.execute(
            "INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?)",
            (clan_id, leader_user_id, int(time.time())),
        )

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error creating clan: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def join_clan(user_id: int, clan_name: str) -> bool:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM clans WHERE name = ?", (clan_name,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return False
        clan_id = row["id"]

        # already in a clan?
        cur.execute("SELECT clan_id FROM clan_members WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            conn.close()
            return False

        # check capacity
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM clan_members WHERE clan_id = ?", (clan_id,)
        )
        cnt = cur.fetchone()["cnt"]
        if cnt >= CLAN_MAX_MEMBERS:
            conn.close()
            return False

        cur.execute(
            "INSERT INTO clan_members (clan_id, user_id, joined_at) VALUES (?, ?, ?)",
            (clan_id, user_id, int(time.time())),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error joining clan: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_clan_info(user_id: int) -> Optional[Dict[str, Any]]:
    """Return clan info for the clan where this user is a member."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.id, c.name, c.leader_id, c.created_at,
               u.username AS leader_username
        FROM clan_members m
        JOIN clans c ON m.clan_id = c.id
        LEFT JOIN users u ON c.leader_id = u.id
        WHERE m.user_id = ?
        """,
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_clan_by_name(name: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.*, u.username AS leader_username
        FROM clans c
        LEFT JOIN users u ON c.leader_id = u.id
        WHERE c.name = ?
        """,
        (name,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_clan_members(clan_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.id AS user_id,
               u.username,
               u.telegram_id,
               u.mew_points
        FROM clan_members m
        JOIN users u ON m.user_id = u.id
        WHERE m.clan_id = ?
        ORDER BY u.mew_points DESC
        """,
        (clan_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def leave_clan(user_id: int) -> bool:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        # figure out which clan
        cur.execute(
            "SELECT clan_id FROM clan_members WHERE user_id = ?", (user_id,)
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return False
        clan_id = row["clan_id"]

        # just delete membership
        cur.execute(
            "DELETE FROM clan_members WHERE user_id = ? AND clan_id = ?",
            (user_id, clan_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error(f"Error leaving clan: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_clan(clan_id: int) -> bool:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM clan_members WHERE clan_id = ?", (clan_id,))
        cur.execute("DELETE FROM clans WHERE id = ?", (clan_id,))
        changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error(f"Error deleting clan: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def transfer_clan_leadership(clan_id: int, new_leader_id: int) -> bool:
    """Not used in main logic yet, but implemented."""
    conn = _get_conn()
    cur = conn.cursor()
    try:
        # new leader must be a member of the clan
        cur.execute(
            "SELECT 1 FROM clan_members WHERE clan_id = ? AND user_id = ?",
            (clan_id, new_leader_id),
        )
        if not cur.fetchone():
            conn.close()
            return False

        cur.execute(
            "UPDATE clans SET leader_id = ? WHERE id = ?",
            (new_leader_id, clan_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error(f"Error transferring clan leadership: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_available_clans() -> List[Dict[str, Any]]:
    """Return clans that are not full (member_count < CLAN_MAX_MEMBERS)."""
    conn = _get_conn()
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
    conn.close()
    clans = []
    for r in rows:
        d = dict(r)
        if d.get("member_count", 0) < CLAN_MAX_MEMBERS:
            clans.append(d)
    return clans


# ========= MARKETPLACE =========

def create_market_listing(
    seller_id: int, cat_id: int, price: int, duration_seconds: int
) -> Optional[int]:
    now = int(time.time())
    expires_at = now + duration_seconds
    conn = _get_conn()
    cur = conn.cursor()
    try:
        # ensure cat belongs to seller and is alive
        cur.execute(
            "SELECT owner_id, alive FROM cats WHERE id = ?", (cat_id,)
        )
        row = cur.fetchone()
        if not row or row["owner_id"] != seller_id or row["alive"] != 1:
            conn.close()
            return None

        # ensure cat not already listed
        cur.execute(
            "SELECT id FROM market_listings WHERE cat_id = ? AND active = 1",
            (cat_id,),
        )
        if cur.fetchone():
            conn.close()
            return None

        cur.execute(
            """
            INSERT INTO market_listings (cat_id, seller_id, price, created_at, expires_at, active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (cat_id, seller_id, price, now, expires_at),
        )
        conn.commit()
        listing_id = cur.lastrowid
        return listing_id
    except Exception as e:
        logger.error(f"Error creating market listing: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def _cleanup_expired_listings(cur):
    now = int(time.time())
    cur.execute(
        "UPDATE market_listings SET active = 0 WHERE active = 1 AND expires_at < ?",
        (now,),
    )


def get_market_listings() -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        _cleanup_expired_listings(cur)
        conn.commit()

        cur.execute(
            """
            SELECT * FROM market_listings
            WHERE active = 1
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_user_market_listings(user_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        _cleanup_expired_listings(cur)
        conn.commit()

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
    finally:
        conn.close()


def cancel_market_listing(listing_id: int, user_id: int) -> bool:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE market_listings
            SET active = 0
            WHERE id = ? AND seller_id = ? AND active = 1
            """,
            (listing_id, user_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error(f"Error canceling market listing: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def buy_market_listing(listing_id: int, buyer_db_id: int) -> Optional[Dict[str, Any]]:
    """
    Atomically:
    - check listing exists & active & not expired
    - check buyer has enough mew_points
    - transfer cat owner
    - move money (buyer -> seller, minus fee)
    - mark listing inactive
    Returns a dict with info or None on failure.
    """
    conn = _get_conn()
    conn.isolation_level = "EXCLUSIVE"
    cur = conn.cursor()
    try:
        _cleanup_expired_listings(cur)

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
            conn.commit()
            conn.close()
            return None

        listing = dict(listing)
        price = listing["price"]
        cat_id = listing["cat_id"]
        seller_id = listing["seller_id"]

        if buyer_db_id == seller_id:
            conn.commit()
            conn.close()
            return None

        # load buyer & seller
        cur.execute("SELECT * FROM users WHERE id = ?", (buyer_db_id,))
        buyer = cur.fetchone()
        if not buyer:
            conn.commit()
            conn.close()
            return None
        buyer = dict(buyer)

        cur.execute("SELECT * FROM users WHERE id = ?", (seller_id,))
        seller = cur.fetchone()
        if not seller:
            conn.commit()
            conn.close()
            return None
        seller = dict(seller)

        if buyer["mew_points"] < price:
            conn.commit()
            conn.close()
            return None

        fee = int(price * MARKET_FEE_PERCENT / 100)
        net_amount = price - fee

        # update balances
        cur.execute(
            "UPDATE users SET mew_points = mew_points - ? WHERE id = ?",
            (price, buyer_db_id),
        )
        cur.execute(
            "UPDATE users SET mew_points = mew_points + ? WHERE id = ?",
            (net_amount, seller_id),
        )

        # transfer cat
        cur.execute(
            "UPDATE cats SET owner_id = ? WHERE id = ?", (buyer_db_id, cat_id)
        )

        # deactivate listing
        cur.execute(
            "UPDATE market_listings SET active = 0 WHERE id = ?", (listing_id,)
        )

        conn.commit()

        result = {
            "listing_id": listing_id,
            "price": price,
            "cat_id": cat_id,
            "seller_id": seller_id,
            "fee": fee,
            "net_amount": net_amount,
        }
        return result
    except Exception as e:
        logger.error(f"Error buying market listing: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


# ========= BREEDING =========

def breed_cats(
    parent1_id: int,
    parent2_id: int,
    child_id: Optional[int],
    success: bool,
):
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO cat_breeding (parent1_id, parent2_id, child_id, success, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (parent1_id, parent2_id, child_id, 1 if success else 0, int(time.time())),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error recording breeding: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_cat_offspring(parent_cat_id: int) -> List[Dict[str, Any]]:
    """Return all children that have this cat as parent."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.*, c.name AS child_name, c.owner_id AS child_owner_id
        FROM cat_breeding b
        LEFT JOIN cats c ON b.child_id = c.id
        WHERE b.parent1_id = ? OR b.parent2_id = ?
        ORDER BY b.created_at DESC
        """,
        (parent_cat_id, parent_cat_id),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_special_cats(owner_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM cats WHERE owner_id = ? AND is_special = 1 AND alive = 1",
        (owner_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ========= DAILY / ACTIVE EVENTS =========

def get_daily_event_count(chat_id: int, date_str: str) -> int:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT count FROM daily_events WHERE chat_id = ? AND date = ?",
        (chat_id, date_str),
    )
    row = cur.fetchone()
    conn.close()
    return row["count"] if row else 0


def update_daily_event_count(chat_id: int, date_str: str, new_count: int):
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO daily_events (chat_id, date, count)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, date) DO UPDATE SET count = excluded.count
            """,
            (chat_id, date_str, new_count),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error updating daily_event_count: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_active_events(chat_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM active_events
        WHERE chat_id = ?
        ORDER BY created_at DESC
        """,
        (chat_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_active_event(
    chat_id: int, event_id: str, text: str, expected_answer: str
):
    conn = _get_conn()
    cur = conn.cursor()
    try:
        # ensure only one active event per chat at a time
        cur.execute("DELETE FROM active_events WHERE chat_id = ?", (chat_id,))
        cur.execute(
            """
            INSERT INTO active_events (chat_id, event_id, text, expected_answer, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, event_id, text, expected_answer, int(time.time())),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error creating active event: {e}")
        conn.rollback()
    finally:
        conn.close()


def delete_active_event(chat_id: int):
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM active_events WHERE chat_id = ?", (chat_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Error deleting active event: {e}")
        conn.rollback()
    finally:
        conn.close()
