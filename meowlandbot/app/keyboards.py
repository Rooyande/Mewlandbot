from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def owner_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add Admin",
                    callback_data="owner:add_admin"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📂 Manage Folders",
                    callback_data="owner:folders"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Lists",
                    callback_data="owner:lists"
                )
            ],
        ]
    )


def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add Safe User",
                    callback_data="admin:add_safe"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔓 Unban User",
                    callback_data="admin:unban"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📂 Folders",
                    callback_data="admin:folders"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Lists",
                    callback_data="admin:lists"
                )
            ],
        ]
    )


def confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirm",
                    callback_data=f"confirm:{action}"
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="cancel"
                ),
            ]
        ]
    )
