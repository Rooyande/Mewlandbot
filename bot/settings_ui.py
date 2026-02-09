# bot/settings_ui.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from settings import get_user_settings, toggle_notify, toggle_public_profile, cycle_lang


def settings_root_kb(s: dict) -> InlineKeyboardMarkup:
    notify = "On" if int(s.get("notify", 1)) else "Off"
    pub = "On" if int(s.get("public_profile", 1)) else "Off"
    lang = "FA" if (s.get("lang") == "fa") else "EN"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"Notify: {notify}", callback_data="set:notify")],
            [InlineKeyboardButton(f"Public Profile: {pub}", callback_data="set:pub")],
            [InlineKeyboardButton(f"Language: {lang}", callback_data="set:lang")],
            [InlineKeyboardButton("Back", callback_data="nav:home")],
        ]
    )


async def settings_root_text(user_id: int) -> str:
    s = await get_user_settings(user_id)
    notify = "On" if int(s.get("notify", 1)) else "Off"
    pub = "On" if int(s.get("public_profile", 1)) else "Off"
    lang = "FA" if (s.get("lang") == "fa") else "EN"
    return f"Settings\n\nNotify: {notify}\nPublic Profile: {pub}\nLanguage: {lang}"


async def settings_handle(user_id: int, action: str) -> dict:
    if action == "notify":
        return await toggle_notify(user_id)
    if action == "pub":
        return await toggle_public_profile(user_id)
    if action == "lang":
        return await cycle_lang(user_id)
    return await get_user_settings(user_id)
