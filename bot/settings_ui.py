from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from settings import get_user_settings, toggle_notify, toggle_public_profile, cycle_lang


def settings_kb(s: dict) -> InlineKeyboardMarkup:
    notify = "On" if int(s.get("notify", 1)) else "Off"
    pub = "On" if int(s.get("public_profile", 1)) else "Off"
    lang = "FA" if s.get("lang") == "fa" else "EN"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"Notify: {notify}", callback_data="set:notify")],
            [InlineKeyboardButton(f"Public Profile: {pub}", callback_data="set:pub")],
            [InlineKeyboardButton(f"Language: {lang}", callback_data="set:lang")],
            [InlineKeyboardButton("Back", callback_data="nav:home")],
        ]
    )


async def settings_text(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    s = await get_user_settings(user_id)
    notify = "On" if int(s.get("notify", 1)) else "Off"
    pub = "On" if int(s.get("public_profile", 1)) else "Off"
    lang = "FA" if s.get("lang") == "fa" else "EN"

    txt = "Settings\n\n" f"Notify: {notify}\nPublic Profile: {pub}\nLanguage: {lang}"
    return txt, settings_kb(s)


async def settings_apply(user_id: int, action: str) -> tuple[str, InlineKeyboardMarkup]:
    if action == "notify":
        s = await toggle_notify(user_id)
    elif action == "pub":
        s = await toggle_public_profile(user_id)
    elif action == "lang":
        s = await cycle_lang(user_id)
    else:
        s = await get_user_settings(user_id)

    notify = "On" if int(s.get("notify", 1)) else "Off"
    pub = "On" if int(s.get("public_profile", 1)) else "Off"
    lang = "FA" if s.get("lang") == "fa" else "EN"

    txt = "Settings\n\n" f"Notify: {notify}\nPublic Profile: {pub}\nLanguage: {lang}"
    return txt, settings_kb(s)
