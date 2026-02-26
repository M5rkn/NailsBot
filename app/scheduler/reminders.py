from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

from app.constants import DATETIME_FMT
from app.db.sqlite import Booking, Database
from app.utils.time import tznow


@dataclass(slots=True)
class ReminderScheduler:
    """
    APScheduler-обёртка:
    - создаём задачи при записи
    - удаляем при отмене
    - восстанавливаем при старте из БД
    """

    bot: Bot
    db: Database
    timezone: str

    def __post_init__(self) -> None:
        self._tz = ZoneInfo(self.timezone)
        self._sched = AsyncIOScheduler(timezone=self._tz)

    @staticmethod
    def job_id_for(booking_id: int) -> str:
        return f"reminder:{booking_id}"

    async def start(self) -> None:
        self._sched.start()
        await self.restore_jobs()

    async def shutdown(self) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=False)

    async def restore_jobs(self) -> None:
        """Восстановить задачи напоминаний после рестарта."""
        now = tznow(self.timezone).replace(tzinfo=None)
        bookings = await self.db.list_pending_reminders(now=now)
        for b in bookings:
            if not b.remind_at or not b.reminder_job_id:
                continue
            try:
                run_dt = datetime.strptime(b.remind_at, DATETIME_FMT).replace(tzinfo=self._tz)
            except ValueError:
                continue
            # На всякий: если в прошлом — не ставим
            if run_dt <= tznow(self.timezone):
                continue
            self._add_job(booking_id=b.id, run_dt=run_dt, job_id=b.reminder_job_id)

    def _add_job(self, *, booking_id: int, run_dt: datetime, job_id: str) -> None:
        # replace_existing=True — чтобы восстановление/перезапись работали
        self._sched.add_job(
            self._fire,
            trigger="date",
            run_date=run_dt,
            id=job_id,
            replace_existing=True,
            kwargs={"booking_id": booking_id},
            misfire_grace_time=60 * 60,  # 1 час
        )

    async def plan_for_booking(self, booking: Booking) -> None:
        """
        Создать задачу за 24 часа до визита.
        Если меньше 24 часов — не создаём.
        """
        visit_dt = datetime.strptime(f"{booking.date} {booking.time}", "%Y-%m-%d %H:%M").replace(tzinfo=self._tz)
        now = tznow(self.timezone)
        remind_dt = visit_dt - timedelta(hours=24)

        if remind_dt <= now:
            # Если запись создана менее чем за 24 часа — напоминание НЕ создаём
            await self.db.clear_booking_reminder(booking.id)
            return

        job_id = self.job_id_for(booking.id)
        self._add_job(booking_id=booking.id, run_dt=remind_dt, job_id=job_id)
        await self.db.set_booking_reminder(booking.id, job_id=job_id, remind_at=remind_dt.replace(tzinfo=None))

    async def delete_for_booking(self, booking: Booking) -> None:
        """Удалить задачу напоминания (если была)."""
        if booking.reminder_job_id:
            try:
                self._sched.remove_job(booking.reminder_job_id)
            except Exception:
                # Если задачи нет (например, после рестарта и удаления) — игнорируем
                pass
        await self.db.clear_booking_reminder(booking.id)

    async def _fire(self, booking_id: int) -> None:
        booking = await self.db.get_booking(booking_id)
        if not booking or booking.status != "active":
            return
        if booking.remind_sent == 1:
            return

        # Требование: текст напоминания (оставляем как в ТЗ)
        text = (
            f"Напоминаем, что вы записаны на наращивание ресниц завтра в {booking.time}.\n"
            f"Ждём вас ️"
        )
        await self.bot.send_message(chat_id=booking.user_id, text=text)
        await self.db.mark_reminder_sent(booking_id)

