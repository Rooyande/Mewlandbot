import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "meowland.db").strip()

# Join Gate
REQUIRED_GROUP_CHAT_ID = int(os.getenv("REQUIRED_GROUP_CHAT_ID", "0"))
REQUIRED_GROUP_INVITE_LINK = os.getenv("REQUIRED_GROUP_INVITE_LINK", "").strip()

# Admin
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Economy (Meow)
MEOW_REWARD = int(os.getenv("MEOW_REWARD", "1"))
MEOW_COOLDOWN_SEC = int(os.getenv("MEOW_COOLDOWN_SEC", "15"))
MEOW_DAILY_LIMIT = int(os.getenv("MEOW_DAILY_LIMIT", "200"))
