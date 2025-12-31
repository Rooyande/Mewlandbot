# handlers/__init__.py
from __future__ import annotations

from aiogram.dispatcher import Dispatcher

from . import start
from . import mew
from . import profile
from . import cats
from . import leaderboard
from . import market
from . import clan
from . import achievements


def register_all(dp: Dispatcher) -> None:
    start.register(dp)
    mew.register(dp)
    profile.register(dp)
    cats.register(dp)
    leaderboard.register(dp)
    market.register(dp)
    clan.register(dp)
    achievements.register(dp)
