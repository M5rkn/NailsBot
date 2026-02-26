from __future__ import annotations

from datetime import datetime

from zoneinfo import ZoneInfo


def tznow(tz: str) -> datetime:
    """Текущее время в заданном часовом поясе."""
    return datetime.now(tz=ZoneInfo(tz))


def to_tz(dt: datetime, tz: str) -> datetime:
    """Привести datetime к часовому поясу tz (если naive — считаем что он уже tz)."""
    zone = ZoneInfo(tz)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=zone)
    return dt.astimezone(zone)

