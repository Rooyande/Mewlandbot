from aiogram.dispatcher import Dispatcher
from handlers import start


def register_all(dp: Dispatcher):
    start.register(dp)

