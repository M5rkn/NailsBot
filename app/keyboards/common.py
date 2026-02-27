from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class MenuCB(CallbackData, prefix="menu"):
    action: str


class SubCB(CallbackData, prefix="sub"):
    action: str  # check


def main_menu_kb(is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗓 Записаться", callback_data=MenuCB(action="book").pack())
    kb.button(text="📌 Моя запись / Отмена", callback_data=MenuCB(action="my").pack())
    kb.button(text="💰 Прайсы", callback_data=MenuCB(action="prices").pack())
    kb.button(text="🖼 Портфолио", callback_data=MenuCB(action="portfolio").pack())
    kb.button(text="📅 Расписание", url="https://t.me/myhappynailss")
    if is_admin:
        kb.button(text="🛠 Админ-панель", callback_data=MenuCB(action="admin").pack())
    kb.adjust(1)
    return kb.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data=MenuCB(action="menu").pack())
    return kb.as_markup()


def subscribe_required_kb(channel_link: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Подписаться", url=channel_link))
    kb.row(InlineKeyboardButton(text="🔄 Проверить подписку", callback_data=SubCB(action="check").pack()))
    kb.row(InlineKeyboardButton(text="⬅️ В меню", callback_data=MenuCB(action="menu").pack()))
    return kb.as_markup()

