import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from app.config import BOT_TOKEN


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def main() -> None:
    setup_logging()

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Prevent webhook/polling conflict
    await bot.delete_webhook(drop_pending_updates=True)

    # Lazy import so the package exists even before we create handlers
    from app.handlers import include_all_routers

    include_all_routers(dp)

    logging.getLogger("eclis").info("ECLIS Guard Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

