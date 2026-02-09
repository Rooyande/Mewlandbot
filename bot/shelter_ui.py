# bot/shelter_ui.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import open_db
from essence import get_essence
from shelter import get_shelter_state, get_next_upgrade_cost, upgrade_shelter


def shelter_kb(can_upgrade: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if can_upgrade:
        rows.append([InlineKeyboardButton("Upgrade", callback_data="shelter:up")])
    rows.append([InlineKeyboardButton("Back", callback_data="nav:home")])
    return InlineKeyboardMarkup(rows)


async def shelter_text(user_id: int) -> str:
    st = await get_shelter_state(user_id)
    if st is None:
        return "Shelter\n\nNot found."

    ess = await get_essence(user_id)

    db = await open_db()
    try:
        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (int(user_id),))
        u = await cur.fetchone()
        mp = 0 if u is None else int(u["mp_balance"] or 0)
    finally:
        await db.close()

    cost = await get_next_upgrade_cost(user_id)

    base = (
        "Shelter\n\n"
        f"Level: {st.level}\n"
        f"Max Cats: {st.effects.max_cats}\n"
        f"Item Slots: {st.effects.item_slots}\n"
        f"Passive Cap: {st.effects.passive_cap_hours}h\n\n"
        f"MP: {mp}\n"
        f"Essence: {ess}\n"
    )

    if cost is None:
        return base

    if cost.mp == 0 and cost.essence == 0:
        return base + "\nMax level."

    return base + f"\nUpgrade Cost:\n- {cost.mp} MP\n- {cost.essence} Essence"


async def shelter_upgrade_and_text(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    res = await upgrade_shelter(user_id)
    if not res.ok:
        if res.reason == "no_mp":
            return "MP کافی نیست.", shelter_kb(True)
        if res.reason == "no_essence":
            return "Essence کافی نیست.", shelter_kb(True)
        if res.reason == "max_level":
            return "Shelter در Max Level است.", shelter_kb(False)
        return "Error.", shelter_kb(True)

    txt = (
        "Upgrade موفق\n\n"
        f"Level: {res.old_level} → {res.new_level}\n"
        f"Cost: {res.cost.mp} MP + {res.cost.essence} Essence\n\n"
        f"Max Cats: {res.effects.max_cats}\n"
        f"Item Slots: {res.effects.item_slots}\n"
        f"Passive Cap: {res.effects.passive_cap_hours}h"
    )
    return txt, shelter_kb(True)
