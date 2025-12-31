import time
from db.db import session


def init_db():
    with session() as conn:
        cur = conn.cursor()

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

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_groups (
                user_id   INTEGER NOT NULL,
                chat_id   INTEGER NOT NULL,
                joined_at INTEGER DEFAULT (strftime('%s','now')),
                PRIMARY KEY (user_id, chat_id)
            );
            """
        )

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

        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_mew_points ON users(mew_points DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cats_owner ON cats(owner_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_market_active ON market_listings(active, expires_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clan_members_clan ON clan_members(clan_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_active_events_chat ON active_events(chat_id);")


def housekeeping():
    """پاکسازی سبک برای داده‌های قدیمی (اختیاری)"""
    cutoff_daily = int(time.time()) - 60 * 24 * 3600
    cutoff_daily_date = time.strftime("%Y-%m-%d", time.gmtime(cutoff_daily))
    cutoff_active = int(time.time()) - 48 * 3600

    with session() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM daily_events WHERE date < ?", (cutoff_daily_date,))
        cur.execute("DELETE FROM active_events WHERE created_at < ?", (cutoff_active,))

