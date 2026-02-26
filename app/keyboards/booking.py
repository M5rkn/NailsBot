from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.common import MenuCB


class TimeCB(CallbackData, prefix="time"):
    date: str  # YYYY-MM-DD
    time: str  # HH:MM


class BookingCB(CallbackData, prefix="book"):
    action: str  # confirm/cancel


def times_kb(date: str, times: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in times:
        kb.button(text=f"🕒 {t}", callback_data=TimeCB(date=date, time=t).pack())
    kb.adjust(2)
    kb.row()
    kb.button(text="⬅️ В меню", callback_data=MenuCB(action="menu").pack())
    return kb.as_markup()


def confirm_booking_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=BookingCB(action="confirm").pack())
    kb.button(text="❌ Отменить", callback_data=BookingCB(action="cancel").pack())
    kb.adjust(1)
    return kb.as_markup()


def cancel_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, отменить", callback_data=BookingCB(action="confirm_cancel").pack())
    kb.button(text="⬅️ Назад", callback_data=MenuCB(action="menu").pack())
    kb.adjust(1)
    return kb.as_markup()

