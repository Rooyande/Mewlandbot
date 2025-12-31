from aiogram.dispatcher import Dispatcher
from handlers import start
from handlers import mew
from handlers import profile
from handlers import cats


def register_all(dp: Dispatcher):
    start.register(dp)
    mew.register(dp)
    profile.register(dp)
    cats.register(dp)
