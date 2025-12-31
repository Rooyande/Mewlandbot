from aiogram import types
from aiogram.dispatcher import Dispatcher


def register(dp: Dispatcher):
    @dp.message_handler(commands=["start", "help"])
    async def start_cmd(message: types.Message):
        await message.reply(
            "😺 میولند\n\n"
            "دستورات:\n"
            "- mew (متنی)\n"
            "- /profile\n"
            "- /adopt [rarity]\n"
            "- /cats\n"
            "- /feed <cat_id> <amount>\n"
            "- /play <cat_id>\n"
            "- /leaderboard\n"
        )
