from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, Response
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
_init_error: str | None = None


async def _init():
    global _bot, _dp, _db, _scheduler, _initialized, _init_error
    if _initialized:
        return

    try:
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
        _init_error = None
        print("[INFO] Bot initialized successfully")
    except Exception as e:
        _init_error = traceback.format_exc()
        print(f"[ERROR] _init failed:\n{_init_error}")
        raise


@app.post("/api/webhook")
async def webhook(request: Request):
    print("[INFO] Webhook called")
    try:
        await _init()
        data = await request.json()
        update = Update.model_validate(data, context={"bot": _bot})
        await _dp.feed_update(_bot, update)
    except Exception as e:
        print(f"[ERROR] webhook: {traceback.format_exc()}")
    return Response(status_code=200)


@app.get("/")
async def health():
    return {"status": "ok", "initialized": _initialized}


@app.get("/debug")
async def debug():
    try:
        await _init()
    except Exception:
        pass
    return {
        "initialized": _initialized,
        "init_error": _init_error,
        "env": {
            "BOT_TOKEN": "set" if os.environ.get("BOT_TOKEN") else "MISSING",
            "ADMIN_ID": os.environ.get("ADMIN_ID", "MISSING"),
            "CHANNEL_ID": os.environ.get("CHANNEL_ID", "MISSING"),
            "CHANNEL_LINK": os.environ.get("CHANNEL_LINK", "MISSING"),
            "SCHEDULE_CHANNEL_ID": os.environ.get("SCHEDULE_CHANNEL_ID", "MISSING"),
            "DB_PATH": os.environ.get("DB_PATH", "/tmp/bot.db"),
        },
        "python": sys.version,
    }
