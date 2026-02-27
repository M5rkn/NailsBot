from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config

from app.db.sqlite import Database
from app.handlers import admin, booking, prices_portfolio, start
from app.scheduler.reminders import ReminderScheduler


async def main() -> None:
    cfg = load_config()

    # Готовим папку под базу
    db_dir = os.path.dirname(os.path.abspath(cfg.db_path))
    print(f"[DEBUG] DB path: {cfg.db_path}")
    print(f"[DEBUG] DB dir: {db_dir}")
    
    if db_dir and not os.path.exists(db_dir):
        print(f"[DEBUG] Creating directory: {db_dir}")
        os.makedirs(db_dir, exist_ok=True)
    
    # Проверка прав на запись
    try:
        test_file = os.path.join(db_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        print(f"[DEBUG] Write test: OK")
    except Exception as e:
        print(f"[ERROR] Cannot write to {db_dir}: {e}")

    bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    db = Database(cfg.db_path)
    print(f"[DEBUG] Connecting to DB...")
    await db.connect()
    print(f"[DEBUG] Initializing DB...")
    await db.init()
    print(f"[DEBUG] DB ready")

    reminder_scheduler = ReminderScheduler(bot=bot, db=db, timezone=cfg.timezone)
    await reminder_scheduler.start()

    # Роутеры
    dp.include_router(start.router)
    dp.include_router(prices_portfolio.router)
    dp.include_router(booking.get_router(cfg=cfg, db=db, reminders=reminder_scheduler))
    dp.include_router(admin.get_router(cfg=cfg, db=db, reminders=reminder_scheduler))

    print(f"[INFO] Bot started successfully!")
    try:
        await dp.start_polling(bot)
    finally:
        await reminder_scheduler.shutdown()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

