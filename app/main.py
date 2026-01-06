import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config.settings import settings
from app.bot.routers.public import router as public_router
from app.bot.routers.admin import router as admin_router
from app.bot.routers.admin_cats import router as admin_cats_router
from app.bot.routers.cats import router as cats_router
from app.bot.routers.shop import router as shop_router  # ✅ NEW

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    bot = Bot(token=settings.bot_token)

    # ✅ FSM Storage
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # routers (ترتیب مهم نیست، ولی admin بهتره بالا باشه)
    dp.include_router(admin_router)
    dp.include_router(admin_cats_router)
    dp.include_router(shop_router)      # ✅ NEW
    dp.include_router(cats_router)
    dp.include_router(public_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
