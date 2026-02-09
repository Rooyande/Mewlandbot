from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db import open_db


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("My Cats", callback_data="nav:cats")],
            [
                InlineKeyboardButton("Inventory", callback_data="nav:inv"),
                InlineKeyboardButton("Shop", callback_data="nav:shop"),
            ],
            [
                InlineKeyboardButton("Events", callback_data="nav:events"),
                InlineKeyboardButton("Settings", callback_data="nav:settings"),
            ],
        ]
    )


def back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="nav:home")]])


async def render_home_text(user_id: int) -> str:
    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT mp_balance, shelter_level, passive_cap_hours FROM users WHERE user_id=?",
            (user_id,),
        )
        u = await cur.fetchone()

        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (user_id,))
        r = await cur.fetchone()

        cur = await db.execute(
            "SELECT COUNT(1) AS c FROM user_cats WHERE user_id=? AND status='active'",
            (user_id,),
        )
        c = await cur.fetchone()

        mp = 0 if u is None else int(u["mp_balance"] or 0)
        shelter = 1 if u is None else int(u["shelter_level"] or 1)
        cap = 0 if u is None else int(u["passive_cap_hours"] or 0)
        essence = 0 if r is None else int(r["essence"] or 0)
        cats = 0 if c is None else int(c["c"] or 0)

        return (
            "Home\n\n"
            f"MP: {mp}\n"
            f"Essence: {essence}\n"
            f"Shelter: {shelter}\n"
            f"Active Cats: {cats}\n"
            f"Passive Cap (hours): {cap if cap else 'default'}"
        )
    finally:
        await db.close()
