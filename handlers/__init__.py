from aiogram.dispatcher import Dispatcher
from handlers import start
from handlers import mew
from handlers import profile
from handlers import cats
from handlers import leaderboard
from handlers import market
from handlers import clan
from handlers import achievements


def register_all(dp: Dispatcher):
    start.register(dp)
    mew.register(dp)
    profile.register(dp)
    cats.register(dp)
    leaderboard.register(dp)
    market.register(dp)
    clan.register(dp)
    achievements.register(dp)
