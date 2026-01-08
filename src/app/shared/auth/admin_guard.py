from __future__ import annotations

from typing import Optional

from aiogram.types import Message
from app.shared.config.settings import Settings


def is_admin_user(user_id: Optional[int], settings: Settings) -> bool:
    if user_id is None:
        return False
    return int(user_id) == int(settings.admin_telegram_id)


def assert_admin_message(message: Message, settings: Settings) -> bool:
    """
    Returns True if admin, otherwise replies with access denied and returns False.
    Intended for admin-only handlers (PV panel).
    """
    user_id = message.from_user.id if message.from_user else None
    if not is_admin_user(user_id, settings):
        # Do not leak any extra info
        try:
            # reply only if possible
            return False
        except Exception:
            return False
    return True
