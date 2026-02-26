from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import aiosqlite

from app.constants import DATETIME_FMT, DATE_FMT, TIME_FMT


@dataclass(slots=True)
class Booking:
    id: int
    user_id: int
    date: str
    time: str
    name: str
    phone: str
    status: str
    created_at: str
    reminder_job_id: Optional[str]
    remind_at: Optional[str]
    remind_sent: int


class Database:
    """Простой слой доступа к SQLite (aiosqlite)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.execute("PRAGMA synchronous = NORMAL;")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("DB is not connected")
        return self._conn

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def init(self) -> None:
        """Создание таблиц (если их нет)."""
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS working_days (
              date TEXT PRIMARY KEY,           -- YYYY-MM-DD
              is_closed INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS bookings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              date TEXT NOT NULL,              -- YYYY-MM-DD
              time TEXT NOT NULL,              -- HH:MM
              name TEXT NOT NULL,
              phone TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',  -- active/cancelled
              created_at TEXT NOT NULL,        -- YYYY-MM-DD HH:MM:SS
              reminder_job_id TEXT,
              remind_at TEXT,
              remind_sent INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS slots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date TEXT NOT NULL,              -- YYYY-MM-DD
              time TEXT NOT NULL,              -- HH:MM
              is_booked INTEGER NOT NULL DEFAULT 0,
              booking_id INTEGER,
              UNIQUE(date, time),
              FOREIGN KEY(date) REFERENCES working_days(date) ON DELETE CASCADE,
              FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_slots_date ON slots(date);
            CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
            CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date);
            """
        )
        await self.conn.commit()

    # -------- Working days / slots (admin) --------

    async def add_working_day(self, date: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO working_days(date, is_closed) VALUES (?, 0);",
            (date,),
        )
        await self.conn.commit()

    async def set_day_closed(self, date: str, closed: bool) -> None:
        await self.add_working_day(date)
        await self.conn.execute(
            "UPDATE working_days SET is_closed=? WHERE date=?;",
            (1 if closed else 0, date),
        )
        await self.conn.commit()

    async def is_day_closed(self, date: str) -> bool:
        cur = await self.conn.execute(
            "SELECT is_closed FROM working_days WHERE date=?;",
            (date,),
        )
        row = await cur.fetchone()
        return bool(row["is_closed"]) if row else False

    async def add_slot(self, date: str, time: str) -> bool:
        """Добавить слот. True если добавлен, False если уже был."""
        await self.add_working_day(date)
        if await self.is_day_closed(date):
            return False
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO slots(date, time, is_booked) VALUES (?, ?, 0);",
            (date, time),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def delete_slot(self, date: str, time: str) -> bool:
        """Удалить слот (только если не забронирован)."""
        cur = await self.conn.execute(
            "DELETE FROM slots WHERE date=? AND time=? AND is_booked=0;",
            (date, time),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def list_slots(self, date: str) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT date, time, is_booked, booking_id FROM slots WHERE date=? ORDER BY time ASC;",
            (date,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_free_slots(self, date: str) -> list[str]:
        cur = await self.conn.execute(
            """
            SELECT time FROM slots
            WHERE date=? AND is_booked=0
            ORDER BY time ASC;
            """,
            (date,),
        )
        rows = await cur.fetchall()
        return [r["time"] for r in rows]

    async def list_available_dates(self, start_date: str, end_date: str) -> list[str]:
        """
        Даты, где день не закрыт и есть хотя бы один свободный слот.
        start_date/end_date: YYYY-MM-DD (inclusive).
        """
        cur = await self.conn.execute(
            """
            SELECT d.date
            FROM working_days d
            WHERE d.date BETWEEN ? AND ?
              AND d.is_closed = 0
              AND EXISTS (
                SELECT 1 FROM slots s
                WHERE s.date = d.date AND s.is_booked = 0
              )
            ORDER BY d.date ASC;
            """,
            (start_date, end_date),
        )
        rows = await cur.fetchall()
        return [r["date"] for r in rows]

    # -------- Bookings (user/admin) --------

    async def get_user_active_booking(self, user_id: int) -> Optional[Booking]:
        cur = await self.conn.execute(
            """
            SELECT * FROM bookings
            WHERE user_id=? AND status='active'
            ORDER BY id DESC LIMIT 1;
            """,
            (user_id,),
        )
        row = await cur.fetchone()
        return self._row_to_booking(row) if row else None

    async def get_booking(self, booking_id: int) -> Optional[Booking]:
        cur = await self.conn.execute(
            "SELECT * FROM bookings WHERE id=?;",
            (booking_id,),
        )
        row = await cur.fetchone()
        return self._row_to_booking(row) if row else None

    async def get_booking_by_slot(self, date: str, time: str) -> Optional[Booking]:
        cur = await self.conn.execute(
            """
            SELECT b.* FROM bookings b
            WHERE b.date=? AND b.time=? AND b.status='active'
            ORDER BY b.id DESC LIMIT 1;
            """,
            (date, time),
        )
        row = await cur.fetchone()
        return self._row_to_booking(row) if row else None

    async def create_booking(
        self,
        user_id: int,
        date: str,
        time: str,
        name: str,
        phone: str,
        created_at: datetime,
    ) -> tuple[bool, str | Booking]:
        """
        Создать запись на слот (атомарно).
        Возвращает: (ok, booking | error_message)
        """
        # Синхронизация: блокируем на запись транзакцией.
        await self.conn.execute("BEGIN IMMEDIATE;")
        try:
            # 1) Проверка: пользователь уже имеет активную запись
            cur = await self.conn.execute(
                "SELECT id FROM bookings WHERE user_id=? AND status='active' LIMIT 1;",
                (user_id,),
            )
            if await cur.fetchone():
                await self.conn.execute("ROLLBACK;")
                return False, "У вас уже есть активная запись. Сначала отмените её."

            # 2) Проверка: день не закрыт
            cur = await self.conn.execute(
                "SELECT is_closed FROM working_days WHERE date=?;",
                (date,),
            )
            row = await cur.fetchone()
            if not row or int(row["is_closed"]) == 1:
                await self.conn.execute("ROLLBACK;")
                return False, "Этот день недоступен для записи."

            # 3) Проверка: слот существует и свободен
            cur = await self.conn.execute(
                "SELECT id, is_booked FROM slots WHERE date=? AND time=?;",
                (date, time),
            )
            slot = await cur.fetchone()
            if not slot:
                await self.conn.execute("ROLLBACK;")
                return False, "Слот не найден."
            if int(slot["is_booked"]) == 1:
                await self.conn.execute("ROLLBACK;")
                return False, "Этот слот уже занят."

            # 4) Создаём запись
            created_at_s = created_at.strftime(DATETIME_FMT)
            cur = await self.conn.execute(
                """
                INSERT INTO bookings(user_id, date, time, name, phone, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?);
                """,
                (user_id, date, time, name, phone, created_at_s),
            )
            booking_id = int(cur.lastrowid)

            # 5) Бронируем слот
            await self.conn.execute(
                "UPDATE slots SET is_booked=1, booking_id=? WHERE id=?;",
                (booking_id, int(slot["id"])),
            )

            await self.conn.commit()
        except Exception:
            await self.conn.execute("ROLLBACK;")
            raise

        booking = await self.get_booking(booking_id)
        if booking is None:
            return False, "Не удалось создать запись. Попробуйте ещё раз."
        return True, booking

    async def cancel_booking_by_user(self, user_id: int) -> Optional[Booking]:
        booking = await self.get_user_active_booking(user_id)
        if not booking:
            return None
        await self.cancel_booking_by_id(booking.id)
        return booking

    async def cancel_booking_by_id(self, booking_id: int) -> Optional[Booking]:
        await self.conn.execute("BEGIN IMMEDIATE;")
        try:
            booking = await self.get_booking(booking_id)
            if not booking or booking.status != "active":
                await self.conn.execute("ROLLBACK;")
                return None

            # освобождаем слот
            await self.conn.execute(
                "UPDATE slots SET is_booked=0, booking_id=NULL WHERE booking_id=?;",
                (booking_id,),
            )
            # помечаем запись отменённой
            await self.conn.execute(
                "UPDATE bookings SET status='cancelled' WHERE id=?;",
                (booking_id,),
            )
            await self.conn.commit()
            return booking
        except Exception:
            await self.conn.execute("ROLLBACK;")
            raise

    async def list_bookings_by_date(self, date: str) -> list[Booking]:
        cur = await self.conn.execute(
            """
            SELECT * FROM bookings
            WHERE date=? AND status='active'
            ORDER BY time ASC;
            """,
            (date,),
        )
        rows = await cur.fetchall()
        return [self._row_to_booking(r) for r in rows]

    # -------- Reminders --------

    async def set_booking_reminder(self, booking_id: int, job_id: str, remind_at: datetime) -> None:
        await self.conn.execute(
            "UPDATE bookings SET reminder_job_id=?, remind_at=?, remind_sent=0 WHERE id=?;",
            (job_id, remind_at.strftime(DATETIME_FMT), booking_id),
        )
        await self.conn.commit()

    async def clear_booking_reminder(self, booking_id: int) -> None:
        await self.conn.execute(
            "UPDATE bookings SET reminder_job_id=NULL, remind_at=NULL, remind_sent=0 WHERE id=?;",
            (booking_id,),
        )
        await self.conn.commit()

    async def mark_reminder_sent(self, booking_id: int) -> None:
        await self.conn.execute(
            "UPDATE bookings SET remind_sent=1 WHERE id=?;",
            (booking_id,),
        )
        await self.conn.commit()

    async def list_pending_reminders(self, now: datetime) -> list[Booking]:
        cur = await self.conn.execute(
            """
            SELECT * FROM bookings
            WHERE status='active'
              AND reminder_job_id IS NOT NULL
              AND remind_at IS NOT NULL
              AND remind_sent=0;
            """
        )
        rows = await cur.fetchall()
        result: list[Booking] = []
        for r in rows:
            b = self._row_to_booking(r)
            if not b.remind_at:
                continue
            try:
                dt = datetime.strptime(b.remind_at, DATETIME_FMT)
            except ValueError:
                continue
            if dt > now:
                result.append(b)
        return result

    # -------- Utils --------

    @staticmethod
    def _row_to_booking(row: aiosqlite.Row) -> Booking:
        return Booking(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            date=str(row["date"]),
            time=str(row["time"]),
            name=str(row["name"]),
            phone=str(row["phone"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            reminder_job_id=row["reminder_job_id"],
            remind_at=row["remind_at"],
            remind_sent=int(row["remind_sent"]),
        )

