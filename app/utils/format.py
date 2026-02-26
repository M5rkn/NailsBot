from __future__ import annotations

from typing import Iterable


def esc(s: str) -> str:
    """Минимальный escape под HTML parse_mode."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def format_schedule(date: str, slots: Iterable[dict], booked_by: dict[int, str]) -> str:
    """
    Красивое расписание для канала/админа.
    booked_by: booking_id -> name
    """
    lines = [f"📅 <b>Расписание на {esc(date)}</b>"]
    has_any = False
    for s in slots:
        has_any = True
        time = esc(str(s["time"]))
        if int(s["is_booked"]) == 1 and s.get("booking_id") in booked_by:
            name = esc(booked_by[int(s["booking_id"])])
            lines.append(f"✅ <b>{time}</b> — {name}")
        elif int(s["is_booked"]) == 1:
            lines.append(f"✅ <b>{time}</b> — занято")
        else:
            lines.append(f"🟢 <b>{time}</b> — свободно")
    if not has_any:
        lines.append("Нет слотов.")
    return "\n".join(lines)

