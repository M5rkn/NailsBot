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
    service_id: Optional[int]
    service_name: Optional[str]
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

            CREATE TABLE IF NOT EXISTS services (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,              -- Название услуги
              price INTEGER NOT NULL,          -- Цена в рублях
              duration INTEGER NOT NULL,       -- Длительность в минутах
              is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS bookings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              date TEXT NOT NULL,              -- YYYY-MM-DD
              time TEXT NOT NULL,              -- HH:MM
              service_id INTEGER,
              name TEXT NOT NULL,
              phone TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',  -- active/cancelled
              created_at TEXT NOT NULL,        -- YYYY-MM-DD HH:MM:SS
              reminder_job_id TEXT,
              remind_at TEXT,
              remind_sent INTEGER NOT NULL DEFAULT 0,
              FOREIGN KEY(service_id) REFERENCES services(id)
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

        # Добавим услуги по умолчанию, если их нет
        cur = await self.conn.execute("SELECT COUNT(*) as cnt FROM services;")
        row = await cur.fetchone()
        if row["cnt"] == 0:
            await self.conn.execute(
                "INSERT INTO services(name, price, duration, is_active) VALUES (?, ?, ?, ?);",
                ("Френч", 1000, 90, 1),
            )
            await self.conn.execute(
                "INSERT INTO services(name, price, duration, is_active) VALUES (?, ?, ?, ?);",
                ("Квадрат", 500, 60, 1),
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

    async def list_free_slots(self, date: str, service_id: Optional[int] = None) -> list[str]:
        """
        Получить свободные слоты на дату.
        Если указан service_id — показываем только слоты, где хватает времени.
        """
        # Получаем все свободные слоты
        cur = await self.conn.execute(
            """
            SELECT time FROM slots
            WHERE date=? AND is_booked=0
            ORDER BY time ASC;
            """,
            (date,),
        )
        rows = await cur.fetchall()
        all_free = [r["time"] for r in rows]
        
        if not service_id:
            return all_free
        
        # Если есть услуга — фильтруем по длительности
        duration = await self.get_service_duration(service_id)
        available = []
        
        for start_time in all_free:
            required = self._get_required_slots(start_time, duration)
            # Проверяем что все нужные слоты есть и свободны
            if all(t in all_free for t in required):
                available.append(start_time)
        
        return available

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

    async def list_dates_with_slots(self, start_date: str, end_date: str) -> list[str]:
        """
        Даты, где есть слоты (независимо от статуса).
        start_date/end_date: YYYY-MM-DD (inclusive).
        """
        cur = await self.conn.execute(
            """
            SELECT DISTINCT s.date
            FROM slots s
            WHERE s.date BETWEEN ? AND ?
            ORDER BY s.date ASC;
            """,
            (start_date, end_date),
        )
        rows = await cur.fetchall()
        return [r["date"] for r in rows]

    # -------- Bookings (user/admin) --------

    async def get_user_active_booking(self, user_id: int) -> Optional[Booking]:
        cur = await self.conn.execute(
            """
            SELECT b.*, s.name as service_name FROM bookings b
            LEFT JOIN services s ON b.service_id = s.id
            WHERE user_id=? AND status='active'
            ORDER BY id DESC LIMIT 1;
            """,
            (user_id,),
        )
        row = await cur.fetchone()
        return self._row_to_booking(row) if row else None

    async def get_booking_by_slot(self, date: str, time: str) -> Optional[Booking]:
        cur = await self.conn.execute(
            """
            SELECT b.*, s.name as service_name FROM bookings b
            LEFT JOIN services s ON b.service_id = s.id
            WHERE b.date=? AND b.time=? AND b.status='active'
            ORDER BY b.id DESC LIMIT 1;
            """,
            (date, time),
        )
        row = await cur.fetchone()
        return self._row_to_booking(row) if row else None

    async def get_booking(self, booking_id: int) -> Optional[Booking]:
        cur = await self.conn.execute(
            """
            SELECT b.*, s.name as service_name FROM bookings b
            LEFT JOIN services s ON b.service_id = s.id
            WHERE b.id=?;
            """,
            (booking_id,),
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
        service_id: Optional[int] = None,
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

            # 3b) Если есть услуга — проверяем все слоты на длительность
            required_slots = [time]
            if service_id:
                duration = await self.get_service_duration(service_id)
                required_slots = self._get_required_slots(time, duration)
                
                # Проверяем что все слоты свободны
                for slot_time in required_slots:
                    cur = await self.conn.execute(
                        "SELECT id, is_booked FROM slots WHERE date=? AND time=?;",
                        (date, slot_time),
                    )
                    s = await cur.fetchone()
                    if not s:
                        await self.conn.execute("ROLLBACK;")
                        return False, f"Слот {slot_time} недоступен."
                    if int(s["is_booked"]) == 1:
                        await self.conn.execute("ROLLBACK;")
                        return False, f"Слот {slot_time} уже занят."

            # 4) Создаём запись
            created_at_s = created_at.strftime(DATETIME_FMT)
            cur = await self.conn.execute(
                """
                INSERT INTO bookings(user_id, date, time, service_id, name, phone, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?);
                """,
                (user_id, date, time, service_id, name, phone, created_at_s),
            )
            booking_id = int(cur.lastrowid)

            # 5) Бронируем все слоты
            for slot_time in required_slots:
                cur = await self.conn.execute(
                    "SELECT id FROM slots WHERE date=? AND time=?;",
                    (date, slot_time),
                )
                s = await cur.fetchone()
                if s:
                    await self.conn.execute(
                        "UPDATE slots SET is_booked=1, booking_id=? WHERE id=?;",
                        (booking_id, int(s["id"])),
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
            SELECT b.*, s.name as service_name FROM bookings b
            LEFT JOIN services s ON b.service_id = s.id
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

    # -------- Services --------

    async def list_services(self, active_only: bool = True) -> list[dict[str, Any]]:
        """Получить список услуг."""
        if active_only:
            cur = await self.conn.execute(
                "SELECT id, name, price, duration, is_active FROM services WHERE is_active=1 ORDER BY id;"
            )
        else:
            cur = await self.conn.execute(
                "SELECT id, name, price, duration, is_active FROM services ORDER BY id;"
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_service(self, service_id: int) -> Optional[dict[str, Any]]:
        """Получить услугу по ID."""
        cur = await self.conn.execute(
            "SELECT id, name, price, duration, is_active FROM services WHERE id=?;",
            (service_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_service_duration(self, service_id: int) -> int:
        """Получить длительность услуги в минутах."""
        cur = await self.conn.execute(
            "SELECT duration FROM services WHERE id=?;",
            (service_id,),
        )
        row = await cur.fetchone()
        return int(row["duration"]) if row else 60

    def _get_required_slots(self, start_time: str, duration_minutes: int) -> list[str]:
        """
        Рассчитать какие слоты нужны для услуги.
        Слоты каждые 30 минут.
        """
        h, m = map(int, start_time.split(":"))
        start_minutes = h * 60 + m
        end_minutes = start_minutes + duration_minutes
        
        slots = []
        current = start_minutes
        while current < end_minutes:
            h = current // 60
            m = current % 60
            if h > 23:
                break
            slots.append(f"{h:02d}:{m:02d}")
            current += 30  # шаг 30 минут
        
        return slots

    async def add_service(self, name: str, price: int, duration: int) -> int:
        """Добавить услугу. Возвращает ID."""
        cur = await self.conn.execute(
            "INSERT INTO services(name, price, duration, is_active) VALUES (?, ?, ?, 1);",
            (name, price, duration),
        )
        await self.conn.commit()
        return int(cur.lastrowid)

    async def toggle_service(self, service_id: int, active: bool) -> None:
        """Включить/выключить услугу."""
        await self.conn.execute(
            "UPDATE services SET is_active=? WHERE id=?;",
            (1 if active else 0, service_id),
        )
        await self.conn.commit()

    # -------- Utils --------

    @staticmethod
    def _row_to_booking(row: aiosqlite.Row) -> Booking:
        return Booking(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            date=str(row["date"]),
            time=str(row["time"]),
            service_id=row["service_id"],
            service_name=row["service_name"],
            name=str(row["name"]),
            phone=str(row["phone"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            reminder_job_id=row["reminder_job_id"],
            remind_at=row["remind_at"],
            remind_sent=int(row["remind_sent"]),
        )

