from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.common import MenuCB


class ServiceCB(CallbackData, prefix="svc"):
    service_id: int


def services_kb(services: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура с выбором услуг."""
    kb = InlineKeyboardBuilder()
    for s in services:
        duration_h = s["duration"] // 60
        duration_m = s["duration"] % 60
        if duration_h > 0:
            dur_text = f"{duration_h} ч {duration_m} мин" if duration_m > 0 else f"{duration_h} ч"
        else:
            dur_text = f"{duration_m} мин"
        kb.button(
            text=f"▫️ {s['name']} — {s['price']}₽ ({dur_text})",
            callback_data=ServiceCB(service_id=s["id"]).pack(),
        )
    kb.adjust(1)
    kb.row()
    kb.button(text="⬅️ В меню", callback_data=MenuCB(action="menu").pack())
    return kb.as_markup()
