PRAGMA foreign_keys = ON;

-- Table: allowed groups where the bot is permitted to operate
CREATE TABLE IF NOT EXISTS allowed_chats (
  chat_id INTEGER PRIMARY KEY,
  title TEXT,
  added_at INTEGER NOT NULL
);

-- Table: cats catalog
CREATE TABLE IF NOT EXISTS cats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  rarity TEXT NOT NULL,
  price INTEGER NOT NULL,
  image_file_id TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

-- Index for faster lookup by rarity
CREATE INDEX IF NOT EXISTS idx_cats_rarity ON cats(rarity);
