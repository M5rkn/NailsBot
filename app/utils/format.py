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


def format_schedule(date: str, slots: Iterable[dict], booked_by: dict[int, dict], public: bool = False) -> str:
    """
    Красивое расписание для канала/админа.
    booked_by: booking_id -> {"name": str, "service": str}
    public: если True — скрывать имена клиентов
    """
    lines = [f"📅 <b>Расписание на {esc(date)}</b>"]
    has_any = False
    for s in slots:
        has_any = True
        time = esc(str(s["time"]))
        if int(s["is_booked"]) == 1 and s.get("booking_id") in booked_by:
            if public:
                # Публичная версия — без имён
                lines.append(f"✅ <b>{time}</b> — занято")
            else:
                # Версия для админа — с именами
                info = booked_by[int(s["booking_id"])]
                name = esc(info.get("name", "Клиент"))
                service = esc(info.get("service", ""))
                if service:
                    lines.append(f"✅ <b>{time}</b> — {name} ({service})")
                else:
                    lines.append(f"✅ <b>{time}</b> — {name}")
        elif int(s["is_booked"]) == 1:
            lines.append(f"✅ <b>{time}</b> — занято")
        else:
            lines.append(f"🟢 <b>{time}</b> — свободно")
    
    if not has_any:
        lines.append("⚠️ <b>Нет слотов</b> — добавьте через админ-панель")
    
    return "\n".join(lines)

