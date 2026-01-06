from aiogram import Dispatcher

from app.bot.routers import public, admin


def setup_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(public.router)
    return dp

