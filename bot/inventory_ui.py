from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from items import list_user_items


PAGE_SIZE = 7


async def fetch_inventory_page(user_id: int, page: int) -> Tuple[List[dict], bool, bool]:
    all_items = await list_user_items(user_id)
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
                "qty": it.qty,
            }
        )
    return rows, has_prev, has_next


async def inventory_text(user_id: int, page: int) -> str:
    return f"Inventory\n\nPage: {page + 1}"


def inventory_kb(items: List[dict], page: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    rows = []
    for it in items:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{it['name']} • x{it['qty']}",
                    callback_data=f"inv:item:{it['item_id']}",
                )
            ]
        )

    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"inv:list:{page-1}"))
    nav.append(InlineKeyboardButton("Back", callback_data="nav:home"))
    if has_next:
        nav.append(InlineKeyboardButton("Next", callback_data=f"inv:list:{page+1}"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)


async def inventory_item_text(user_id: int, item_name: str, item_type: str, qty: int) -> str:
    return f"Item\n\nName: {item_name}\nType: {item_type}\nQty: {qty}"


def inventory_item_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Back", callback_data="inv:list:0")],
            [InlineKeyboardButton("Home", callback_data="nav:home")],
        ]
    )
