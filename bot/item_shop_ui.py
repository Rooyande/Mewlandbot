from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from item_shop import list_items_for_sale, get_item_for_sale


PAGE_SIZE = 7


def item_shop_root_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Browse Items", callback_data="ishop:list:0")],
            [InlineKeyboardButton("Back", callback_data="nav:shop")],
        ]
    )


async def item_shop_root_text() -> str:
    return "Item Shop"


async def fetch_item_shop_page(page: int) -> Tuple[List[dict], bool, bool]:
    all_items = await list_items_for_sale()
    page = max(0, int(page))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE + 1
    chunk = all_items[start:end]

    has_next = len(chunk) > PAGE_SIZE
    chunk = chunk[:PAGE_SIZE]
    has_prev = page > 0

    rows = []
    for it in chunk:
        rows.append(
            {
                "item_id": it.item_id,
                "name": it.name,
                "type": it.type,
                "price": it.price,
            }
        )
    return rows, has_prev, has_next


async def item_shop_list_text(page: int) -> str:
    return f"Item Shop\n\nPage: {page + 1}"


def item_shop_list_kb(items: List[dict], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    rows = []
    for it in items:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{it['name']} • {it['price']} MP",
                    callback_data=f"ishop:buy:{it['item_id']}",
                )
            ]
        )

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"ishop:list:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data="ishop:root"))
    if has_next:
        nav.append(InlineKeyboardButton("Next", callback_data=f"ishop:list:{page+1}"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)


async def item_buy_confirm_text(item_id: int) -> str:
    it = await get_item_for_sale(item_id)
    if it is None:
        return "Not found."
    return f"Confirm Purchase\n\n{it.name}\nType: {it.type}\nCost: {it.price} MP"


def item_buy_confirm_kb(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm", callback_data=f"ishop:confirm:{item_id}")],
            [InlineKeyboardButton("Back", callback_data="ishop:list:0")],
        ]
    )
