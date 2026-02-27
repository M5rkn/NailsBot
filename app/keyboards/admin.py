from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.common import MenuCB


class AdminCB(CallbackData, prefix="adm"):
    action: str  # menu/add_day/close_day/open_day/add_slot/del_slot/cancel_booking/view/services/toggle_service


class AdminServiceCB(CallbackData, prefix="asvc"):
    service_id: int
    action: str  # toggle


class AdminTimeCB(CallbackData, prefix="atime"):
    date: str
    time: str  # Формат: HH-MM (вместо HH:MM)
    mode: str  # add/del/cancel

    @classmethod
    def pack_time(cls, date: str, time: str, mode: str) -> str:
        """Упаковать время, заменив : на -"""
        time_safe = time.replace(":", "-")
        return cls(date=date, time=time_safe, mode=mode).pack()

    def unpack_time(self) -> str:
        """Распаковать время, заменив - на :"""
        return self.time.replace("-", ":")


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить рабочий день", callback_data=AdminCB(action="add_day").pack())
    kb.button(text="⛔ Закрыть день полностью", callback_data=AdminCB(action="close_day").pack())
    kb.button(text="✅ Открыть день", callback_data=AdminCB(action="open_day").pack())
    kb.button(text="🕒 Добавить временной слот", callback_data=AdminCB(action="add_slot").pack())
    kb.button(text="🗑 Удалить временной слот", callback_data=AdminCB(action="del_slot").pack())
    kb.button(text="❌ Отменить запись клиента", callback_data=AdminCB(action="cancel_booking").pack())
    kb.button(text="📅 Посмотреть расписание на дату", callback_data=AdminCB(action="view").pack())
    kb.button(text="📋 Услуги", callback_data=AdminCB(action="services").pack())
    kb.button(text="⬅️ В меню", callback_data=MenuCB(action="menu").pack())
    kb.adjust(1)
    return kb.as_markup()


def services_admin_kb(services: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура управления услугами для админа."""
    kb = InlineKeyboardBuilder()
    for s in services:
        status = "✅" if s["is_active"] else "❌"
        kb.button(
            text=f"{status} {s['name']} — {s['price']}₽",
            callback_data=AdminServiceCB(service_id=s["id"], action="toggle").pack(),
        )
    kb.adjust(1)
    kb.row()
    kb.button(text="⬅️ Назад", callback_data=AdminCB(action="menu").pack())
    return kb.as_markup()


def admin_times_grid(date: str, *, mode: str) -> InlineKeyboardMarkup:
    """
    Сетка времени каждые 30 минут (09:00 - 20:00).
    Используется для добавления слотов (и потенциально других операций).
    """
    kb = InlineKeyboardBuilder()
    hours = list(range(9, 21))
    times: list[str] = []
    for h in hours:
        for m in (0, 30):
            if h == 20 and m == 30:
                continue
            times.append(f"{h:02d}:{m:02d}")
    for t in times:
        kb.button(text=t, callback_data=AdminTimeCB.pack_time(date=date, time=t, mode=mode))
    kb.adjust(4)
    kb.row()
    kb.button(text="⬅️ Назад", callback_data=AdminCB(action="menu").pack())
    return kb.as_markup()


def admin_existing_slots_kb(date: str, times: list[str], *, mode: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in times:
        kb.button(text=f"🕒 {t}", callback_data=AdminTimeCB.pack_time(date=date, time=t, mode=mode))
    kb.adjust(2)
    kb.row()
    kb.button(text="⬅️ Назад", callback_data=AdminCB(action="menu").pack())
    return kb.as_markup()

