from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import open_db
from shop import list_shop_cats_by_rarity, PRICE_MULTS, DEFAULT_STANDARD_PRICE


PAGE_SIZE = 6
RARITIES = ["Common", "Uncommon", "Rare", "Epic"]


async def _cfg_int(key: str, default: int) -> int:
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
        row = await cur.fetchone()
        if row is None:
            return default
        try:
            return int(row["value"])
        except Exception:
            return default
    finally:
        await db.close()


async def _direct_price_for_rarity(rarity: str) -> int:
    std_price = await _cfg_int("standard_price", DEFAULT_STANDARD_PRICE)
    mult = PRICE_MULTS.get(rarity, 60)
    return int(std_price * mult)


def direct_shop_root_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(r, callback_data=f"dshop:rar:{r}")] for r in RARITIES]
    rows.append([InlineKeyboardButton("Back", callback_data="nav:shop")])
    return InlineKeyboardMarkup(rows)


async def direct_shop_root_text() -> str:
    return "Direct Purchase\n\nRarity را انتخاب کنید."


async def fetch_direct_shop_page(rarity: str, page: int) -> Tuple[List[dict], bool, bool]:
    rarity = rarity if rarity in RARITIES else "Common"
    all_cats = await list_shop_cats_by_rarity(rarity)

    page = max(0, int(page))
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE + 1
    chunk = all_cats[start:end]

    has_next = len(chunk) > PAGE_SIZE
    chunk = chunk[:PAGE_SIZE]
    has_prev = page > 0

    return chunk, has_prev, has_next


async def direct_shop_list_text(rarity: str, page: int) -> str:
    rarity = rarity if rarity in RARITIES else "Common"
    price = await _direct_price_for_rarity(rarity)
    return f"Direct Purchase\n\nRarity: {rarity}\nPrice: {price} MP\nPage: {page + 1}"


def direct_shop_list_kb(rarity: str, cats: List[dict], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    rows = []
    for c in cats:
        cat_id = int(c["cat_id"])
        name = str(c["name"])
        rows.append([InlineKeyboardButton(name, callback_data=f"dshop:buy:{cat_id}")])

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"dshop:list:{rarity}:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data="dshop:root"))
    if has_next:
        nav.append(InlineKeyboardButton("Next", callback_data=f"dshop:list:{rarity}:{page+1}"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)


async def direct_buy_confirm_text(cat_name: str, rarity: str) -> str:
    price = await _direct_price_for_rarity(rarity)
    return f"Confirm Purchase\n\n{cat_name} ({rarity})\nCost: {price} MP"


def direct_buy_confirm_kb(cat_id: int, rarity: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm", callback_data=f"dshop:confirm:{cat_id}")],
            [InlineKeyboardButton("Back", callback_data=f"dshop:rar:{rarity}")],
        ]
    )
