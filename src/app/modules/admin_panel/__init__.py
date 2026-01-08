from __future__ import annotations

import time
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.contracts import ModuleMeta
from app.shared.config.settings import get_settings
from app.shared.auth.admin_guard import is_admin_user


router = Router()


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    settings = get_settings()

    # Only admin can see panel, everyone else gets no response.
    user_id = message.from_user.id if message.from_user else None
    if not is_admin_user(user_id, settings):
        return

    # Must be in private chat only
    if message.chat.type != "private":
        return

    await message.answer(
        "<b>Admin Panel</b>\n"
        "Choose an action:\n\n"
        "1) Manage Allowed Groups\n"
        "2) Manage Cats Catalog\n\n"
        "<i>Next steps will add buttons and commands here.</i>"
    )


class AdminPanelModule:
    meta = ModuleMeta(
        name="admin_panel",
        version="0.1.0",
        description="Private admin panel for bot owner",
    )

    def register(self, root_router: Router) -> None:
        root_router.include_router(router)


module = AdminPanelModule()
