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
) -> InlineKeyboardMarkup:
    """
    Inline календарь на месяц.
    allowed_dates: множество YYYY-MM-DD, которые можно нажимать (остальные показываем как "•").
    rng: диапазон, в котором разрешена навигация.
    """
    kb = InlineKeyboardBuilder()

    month_name = f"{pycal.month_name[month.month]} {month.year}"
    kb.button(
        text=f"📅 {title}: {month_name}",
        callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
    )
    kb.adjust(1)

    # Дни недели
    week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    for w in week:
        kb.button(
            text=w,
            callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
        )
    kb.adjust(7)

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
                    text="•",
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=0, nav="none").pack(),
                )
                continue
            day_str = day_date.strftime(DATE_FMT)
            if day_str in allowed_dates:
                kb.button(
                    text=str(day_num),
                    callback_data=CalCB(scope=scope, y=month.year, m=month.month, d=day_num, nav="none").pack(),
                )
            else:
                kb.button(
                    text="•",
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

