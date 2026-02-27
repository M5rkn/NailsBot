from __future__ import annotations

import calendar as pycal
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.constants import DATE_FMT


class CalCB(CallbackData, prefix="cal"):
    scope: str  # user/admin
    y: int
    m: int
    d: int  # 0 -> nav, else day
    nav: str  # prev/next/none


@dataclass(slots=True)
class CalendarRange:
    start: date
    end: date


def _month_shift(d: date, delta_months: int) -> date:
    y = d.year
    m = d.month + delta_months
    while m < 1:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 1)


def build_calendar(
    *,
    scope: str,
    month: date,
    allowed_dates: set[str],
    rng: CalendarRange,
    title: str,
    dates_with_slots: set[str] = None,
    closed_dates: set[str] = None,
    open_dates: set[str] = None,
) -> InlineKeyboardMarkup:
    """
    Inline календарь на месяц.
    allowed_dates: множество YYYY-MM-DD, которые можно нажимать (есть свободные слоты).
    dates_with_slots: множество YYYY-MM-DD, где есть слоты (для определения занятых дней).
    closed_dates: множество YYYY-MM-DD, которые закрыты.
    open_dates: множество YYYY-MM-DD, которые открыты (is_closed=0).
    rng: диапазон, в котором разрешена навигация.
    """
    kb = InlineKeyboardBuilder()

    if dates_with_slots is None:
        dates_with_slots = allowed_dates

    if closed_dates is None:
        closed_dates = set()

    if open_dates is None:
        open_dates = set()

    month_name = f"{pycal.month_name[month.month]} {month.year}"
    kb.button(
        text=f"📅 {title}: {month_name}",
        callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
    )
    kb.adjust(1)

    cal = pycal.Calendar(firstweekday=0)
    for week_days in cal.monthdayscalendar(month.year, month.month):
        for day_num in week_days:
            if day_num == 0:
                kb.button(
                    text=" ",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
                )
                continue
            day_date = date(month.year, month.month, day_num)
            if day_date < rng.start or day_date > rng.end:
                kb.button(
                    text="—",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
                )
                continue
            day_str = day_date.strftime(DATE_FMT)
            weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][day_date.weekday()]
            
            if day_str in closed_dates and day_str not in allowed_dates:
                # День закрыт админом и не в allowed (не для открытия)
                kb.button(
                    text=f"⛔ {weekday}",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
                )
            elif day_str in closed_dates and day_str in allowed_dates:
                # День закрыт, но в allowed — значит нужно его открыть (admin action)
                kb.button(
                    text=f"⛔ {day_num} {weekday}",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=day_num, nav="none").pack(),
                )
            elif day_str in allowed_dates:
                # День в allowed — кликабельный (для open_day/close_day или есть свободные слоты)
                kb.button(
                    text=f"✅ {day_num} {weekday}",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=day_num, nav="none").pack(),
                )
            elif day_str in open_dates:
                # День открыт (не в allowed, значит нет свободных слотов, но для просмотра показываем ✅)
                kb.button(
                    text=f"✅ {day_num} {weekday}",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=day_num, nav="none").pack(),
                )
            elif day_str in dates_with_slots:
                # Есть слоты, но день не добавлен в working_days
                kb.button(
                    text=f"🈵 {day_num} {weekday}",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=day_num, nav="none").pack(),
                )
            else:
                # Нет слотов или день не добавлен
                kb.button(
                    text=f"❌ {weekday}",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
                )
        kb.adjust(7)

    # Навигация
    prev_month = _month_shift(month, -1)
    next_month = _month_shift(month, +1)

    can_prev = prev_month >= date(rng.start.year, rng.start.month, 1)
    can_next = next_month <= date(rng.end.year, rng.end.month, 1)

    kb.row()
    kb.button(
        text="⬅️",
        callback_data=CalCB(scope=scope, y=prev_month.year, m=prev_month.month, d=0, nav="prev").pack()
        if can_prev
        else CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
    )
    kb.button(
        text="➡️",
        callback_data=CalCB(scope=scope, y=next_month.year, m=next_month.month, d=0, nav="next").pack()
        if can_next
        else CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
    )
    kb.adjust(2)

    return kb.as_markup()

