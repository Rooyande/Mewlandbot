from aiogram.fsm.state import StatesGroup, State


class OwnerStates(StatesGroup):
    waiting_for_admin_id = State()


class AdminStates(StatesGroup):
    waiting_for_safe_user_id = State()
    waiting_for_unban_user_id = State()
