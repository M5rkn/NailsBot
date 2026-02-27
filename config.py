from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    # Telegram
    bot_token: str
    admin_id: int

    # Обязательная подписка (требование)
    channel_id: str  # Теперь может быть юзернейм (@channel) или ID (-100...)
    channel_link: str

    # Канал для публикации расписания (отдельный канал)
    schedule_channel_id: str  # Теперь может быть юзернейм (@channel) или ID (-100...)

    # Системное
    timezone: str
    db_path: str


def load_config() -> Config:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required in .env")

    admin_id = int(os.getenv("ADMIN_ID", "0"))
    if not admin_id:
        raise RuntimeError("ADMIN_ID is required in .env")

    # Теперь поддерживаются юзернеймы (@channel) и ID (-100...)
    channel_id = os.getenv("CHANNEL_ID", "").strip()
    channel_link = os.getenv("CHANNEL_LINK", "").strip()
    if not channel_id or not channel_link:
        raise RuntimeError("CHANNEL_ID and CHANNEL_LINK are required in .env")

    schedule_channel_id = os.getenv("SCHEDULE_CHANNEL_ID", "").strip()
    if not schedule_channel_id:
        raise RuntimeError("SCHEDULE_CHANNEL_ID is required in .env (отдельный канал расписания)")

    timezone = os.getenv("TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"
    db_path = os.getenv("DB_PATH", "./data/bot.db").strip() or "./data/bot.db"

    return Config(
        bot_token=bot_token,
        admin_id=admin_id,
        channel_id=channel_id,
        channel_link=channel_link,
        schedule_channel_id=schedule_channel_id,
        timezone=timezone,
        db_path=db_path,
    )

