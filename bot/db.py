import time
import aiosqlite
from config import DB_PATH

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  mp_balance INTEGER NOT NULL DEFAULT 0,
  last_passive_ts INTEGER,
  shelter_level INTEGER NOT NULL DEFAULT 1,
  passive_cap_hours INTEGER,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
  user_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  window_key TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  last_ts INTEGER,
  PRIMARY KEY (user_id, key),
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_key ON rate_limits(key);

CREATE TABLE IF NOT EXISTS cats_catalog (
  cat_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  rarity TEXT NOT NULL,
  base_passive_rate REAL NOT NULL,
  media_type TEXT NOT NULL,
  media_file_id TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  pools_enabled TEXT NOT NULL,
  available_from INTEGER,
  available_until INTEGER,
  tags TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_cats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  cat_id INTEGER NOT NULL,
  level INTEGER NOT NULL DEFAULT 1,
  dup_counter INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  last_feed_at INTEGER,
  last_play_at INTEGER,
  equipped_items_json TEXT NOT NULL DEFAULT '{}',
  obtained_at INTEGER NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (cat_id) REFERENCES cats_catalog(cat_id)
);

CREATE TABLE IF NOT EXISTS items_catalog (
  item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  effect_json TEXT NOT NULL,
  durability_rules_json TEXT NOT NULL,
  tradable INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  item_id INTEGER NOT NULL,
  qty INTEGER NOT NULL DEFAULT 0,
  durability_state_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (item_id) REFERENCES items_catalog(item_id)
);

CREATE TABLE IF NOT EXISTS resources (
  user_id INTEGER PRIMARY KEY,
  essence INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS economy_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  action TEXT NOT NULL,
  amount INTEGER NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_roles (
  user_id INTEGER PRIMARY KEY,
  role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  admin_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  ts INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_cats_user ON user_cats(user_id);
CREATE INDEX IF NOT EXISTS idx_economy_logs_user_ts ON economy_logs(user_id, ts);
"""

async def open_db() -> aiosqlite.Connection:
  db = await aiosqlite.connect(DB_PATH)
  await db.execute("PRAGMA foreign_keys = ON;")
  db.row_factory = aiosqlite.Row
  return db

async def init_db() -> None:
  db = await open_db()
  try:
    await db.executescript(SCHEMA_SQL)
    await db.commit()
  finally:
    await db.close()

async def set_config(key: str, value: str) -> None:
  now = int(time.time())
  db = await open_db()
  try:
    await db.execute(
      "INSERT INTO config(key, value, updated_at) VALUES(?,?,?) "
      "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
      (key, value, now),
    )
    await db.commit()
  finally:
    await db.close()

async def get_config(key: str) -> str | None:
  db = await open_db()
  try:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    return None if row is None else row["value"]
  finally:
    await db.close()
