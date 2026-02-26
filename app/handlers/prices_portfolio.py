from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from app.keyboards.common import MenuCB, back_to_menu_kb

router = Router()


@router.callback_query(MenuCB.filter(lambda c: c.action == "prices"))
async def prices_cb(call: CallbackQuery) -> None:
    # Требование: без FSM
    text = "<b>Прайсы</b>\n\n" "Френч — <b>1000₽</b>\n" "Квадрат — <b>500₽</b>"
    await call.message.answer(text, reply_markup=back_to_menu_kb())  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(MenuCB.filter(lambda c: c.action == "portfolio"))
async def portfolio_cb(call: CallbackQuery) -> None:
    # Требование: кнопка-ссылка на Pinterest
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Смотреть портфолио", url="https://ru.pinterest.com/crystalwithluv/_created/")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data=MenuCB(action="menu").pack())],
        ]
    )
    await call.message.answer("🖼 <b>Портфолио</b>", reply_markup=kb)  # type: ignore[union-attr]
    await call.answer()

