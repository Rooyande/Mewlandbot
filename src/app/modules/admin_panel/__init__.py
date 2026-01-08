from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.contracts import ModuleMeta
from app.shared.config.settings import get_settings
from app.shared.auth.admin_guard import is_admin_user


router = Router()


def _admin_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Allowed Groups", callback_data="admin:groups")
    kb.button(text="Cats Catalog", callback_data="admin:cats")
    kb.button(text="Close", callback_data="admin:close")
    kb.adjust(1)
    return kb.as_markup()


def _panel_text() -> str:
    return (
        "<b>Admin Panel</b>\n"
        "Select an action:\n\n"
        "• Allowed Groups: whitelist groups where bot can work\n"
        "• Cats Catalog: add/edit/remove cats (photo, rarity, name, price)\n"
    )


def _is_admin_private(message: Message) -> bool:
    settings = get_settings()
    user_id = message.from_user.id if message.from_user else None
    if not is_admin_user(user_id, settings):
        return False
    return message.chat.type == "private"


def _is_admin_callback(query: CallbackQuery) -> bool:
    settings = get_settings()
    user_id = query.from_user.id if query.from_user else None
    return is_admin_user(user_id, settings)


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not _is_admin_private(message):
        return

    await message.answer(_panel_text(), reply_markup=_admin_keyboard())


@router.callback_query()
async def admin_callbacks(query: CallbackQuery) -> None:
    if not _is_admin_callback(query):
        return

    data = (query.data or "").strip()

    if data == "admin:close":
        await query.message.delete()
        await query.answer()
        return

    if data == "admin:groups":
        await query.message.edit_text(
            "<b>Allowed Groups</b>\n"
            "This section will manage the group allowlist.\n\n"
            "<i>Next step will add:</i>\n"
            "• Add current group\n"
            "• Remove group\n"
            "• List allowed groups\n",
            reply_markup=_admin_keyboard(),
        )
        await query.answer()
        return

    if data == "admin:cats":
        await query.message.edit_text(
            "<b>Cats Catalog</b>\n"
            "This section will manage cats stored in database.\n\n"
            "<i>Next step will add:</i>\n"
            "• Add cat (photo + name + rarity + price)\n"
            "• Edit cat\n"
            "• Delete cat\n"
            "• List/Search cats\n",
            reply_markup=_admin_keyboard(),
        )
        await query.answer()
        return

    await query.answer()


class AdminPanelModule:
    meta = ModuleMeta(
        name="admin_panel",
        version="0.2.0",
        description="Private admin panel for bot owner with inline navigation",
    )

    def register(self, root_router: Router) -> None:
        root_router.include_router(router)


module = AdminPanelModule()
