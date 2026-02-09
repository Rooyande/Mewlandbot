from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import open_db
from essence import get_essence
from shelter import get_shelter_state
from passive import get_total_passive_rate


def back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="nav:home")]])


def home_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Meow (+MP)", callback_data="act:meow")],
        [InlineKeyboardButton("My Cats", callback_data="nav:cats")],
        [InlineKeyboardButton("Shop", callback_data="nav:shop")],
        [InlineKeyboardButton("Inventory", callback_data="nav:inv")],
        [InlineKeyboardButton("Shelter", callback_data="nav:shelter")],
        [InlineKeyboardButton("Events", callback_data="nav:events")],
        [InlineKeyboardButton("Settings", callback_data="nav:settings")],
        [InlineKeyboardButton("Feed All", callback_data="nav:feedall")],
        [InlineKeyboardButton("Play All", callback_data="nav:playall")],
    ]
    if int(user_id) == 0:
        pass
    return InlineKeyboardMarkup(rows)


async def render_home_text(user_id: int) -> str:
    db = await open_db()
    try:
        cur = await db.execute("SELECT mp_balance, last_passive_ts, passive_cap_hours, shelter_level FROM users WHERE user_id=?", (int(user_id),))
        u = await cur.fetchone()
        if u is None:
            return "Home\n\nNot found."
        mp = int(u["mp_balance"] or 0)
        cap = u["passive_cap_hours"]
    finally:
        await db.close()

    ess = await get_essence(user_id)
    rate = await get_total_passive_rate(user_id)

    st = await get_shelter_state(user_id)
    lvl = st.level if st else 1
    max_cats = st.effects.max_cats if st else 0

    return (
        "Home\n\n"
        f"MP: {mp}\n"
        f"Essence: {ess}\n"
        f"Passive: {rate:.3f} MP/h\n"
        f"Shelter: L{lvl} (Max Cats: {max_cats})\n"
        f"Passive Cap: {int(cap or (st.effects.passive_cap_hours if st else 24))}h"
    )
