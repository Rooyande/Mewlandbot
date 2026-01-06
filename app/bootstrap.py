import logging

from aiogram import Bot

from app.config.settings import settings
from app.bot.dispatcher import setup_dispatcher


async def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=settings.bot_token)
    dp = setup_dispatcher()

    await dp.start_polling(bot)

