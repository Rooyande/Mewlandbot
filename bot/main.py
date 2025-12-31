import logging
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor

from core.config import load_settings
from db.schema import init_db, housekeeping
from handlers import register_all

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    settings = load_settings()

    init_db()
    housekeeping()

    bot = Bot(token=settings.bot_token, parse_mode=settings.parse_mode)
    dp = Dispatcher(bot, storage=MemoryStorage())

    register_all(dp)

    logger.info("Starting polling...")
    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    main()

