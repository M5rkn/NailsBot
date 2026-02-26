from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    confirming = State()
    cancelling_confirm = State()


class AdminStates(StatesGroup):
    choosing_action = State()
    choosing_date = State()
    choosing_time = State()
    confirming = State()

