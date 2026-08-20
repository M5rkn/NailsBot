from __future__ import annotations

import os

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.db.sqlite import Database
from app.keyboards.common import MenuCB, back_to_menu_kb

router = Router()


@router.callback_query(MenuCB.filter(F.action == "prices"))
async def prices_cb(call: CallbackQuery) -> None:
    db_path = os.environ.get("DB_PATH", "/tmp/bot.db")
    db = Database(db_path)
    await db.connect()
    services = await db.list_services(active_only=True)
    await db.close()

    if not services:
        text = "<b>Прайс-лист</b>\n\nУслуги временно недоступны."
    else:
        lines = ["<b>Прайс-лист</b>\n"]
        for s in services:
            duration_h = s["duration"] // 60
            duration_m = s["duration"] % 60
            if duration_h > 0:
                dur_text = f"{duration_h} ч {duration_m} мин" if duration_m > 0 else f"{duration_h} ч"
            else:
                dur_text = f"{duration_m} мин"
            lines.append(f"▫️ <b>{s['name']}</b> — {s['price']}₽ ({dur_text})")
        text = "\n".join(lines)

    await call.message.answer(text, reply_markup=back_to_menu_kb())
    await call.answer()


@router.callback_query(MenuCB.filter(F.action == "portfolio"))
async def portfolio_cb(call: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Смотреть портфолио", url="https://ru.pinterest.com/thepinkissuecom/")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data=MenuCB(action="menu").pack())],
        ]
    )
    await call.message.answer("🖼 <b>Портфолио</b>", reply_markup=kb)
    await call.answer()
