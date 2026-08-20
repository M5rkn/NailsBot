from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, Response, BackgroundTasks
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from config import load_config
from app.db.sqlite import Database
from app.handlers import admin, booking, prices_portfolio, start
from app.scheduler.reminders import ReminderScheduler

app = FastAPI()

_bot: Bot | None = None
_dp: Dispatcher | None = None
_db: Database | None = None
_scheduler: ReminderScheduler | None = None
_initialized = False


async def _init():
    global _bot, _dp, _db, _scheduler, _initialized
    if _initialized:
        return

    cfg = load_config()
    db_path = os.environ.get("DB_PATH", "/tmp/bot.db")

    _bot = Bot(
        token=cfg.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _dp = Dispatcher(storage=MemoryStorage())
    _db = Database(db_path)
    await _db.connect()
    await _db.init()

    _scheduler = ReminderScheduler(bot=_bot, db=_db, timezone=cfg.timezone)

    _dp.include_router(start.router)
    _dp.include_router(prices_portfolio.router)
    _dp.include_router(booking.get_router(cfg=cfg, db=_db, reminders=_scheduler))
    _dp.include_router(admin.get_router(cfg=cfg, db=_db, reminders=_scheduler))

    _initialized = True


async def _process_update(data: dict):
    try:
        update = Update.model_validate(data, context={"bot": _bot})
        await _dp.feed_update(_bot, update)
    except Exception as e:
        print(f"[ERROR] feed_update: {e}")


@app.post("/api/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    await _init()
    data = await request.json()
    # Возвращаем 200 сразу — Telegram не будет ретраить
    background_tasks.add_task(_process_update, data)
    return Response(status_code=200)


@app.get("/")
async def health():
    return {"status": "ok", "service": "NailsBot"}
