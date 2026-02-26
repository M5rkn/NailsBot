from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.keyboards.common import main_menu_kb
from config import load_config

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    cfg = load_config()
    is_admin = bool(message.from_user and message.from_user.id == cfg.admin_id)
    # admin-кнопка появится в меню в других хендлерах, здесь без конфига/ID
    text = (
        "👋 <b>Привет!</b>\n\n"
        "Я бот для записи к мастеру.\n"
        "Выберите действие:"
    )
    await message.answer(text, reply_markup=main_menu_kb(is_admin=is_admin))

