from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from aiogram import Bot, Router, F
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from app.constants import DATE_FMT, MAX_DAYS_AHEAD
from app.db.sqlite import Booking, Database
from app.fsm.states import BookingStates
from app.keyboards.booking import BookingCB, TimeCB, cancel_confirm_kb, confirm_booking_kb, times_kb
from app.keyboards.calendar import CalendarRange, CalCB, build_calendar
from app.keyboards.common import MenuCB, SubCB, main_menu_kb, subscribe_required_kb
from app.keyboards.services import ServiceCB, services_kb
from app.scheduler.reminders import ReminderScheduler
from app.utils.format import esc, format_schedule
from app.utils.time import tznow


@dataclass(slots=True)
class BookingDeps:
    cfg: object
    db: Database
    reminders: ReminderScheduler


def get_router(*, cfg, db: Database, reminders: ReminderScheduler) -> Router:
    router = Router()
    deps = BookingDeps(cfg=cfg, db=db, reminders=reminders)

   

    async def is_subscribed(bot: Bot, user_id: int) -> bool:
        try:
            member = await bot.get_chat_member(chat_id=cfg.channel_id, user_id=user_id)
            return member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
        except TelegramForbiddenError:
          
            return False
        except TelegramBadRequest as e:
            
            print(f"[DEBUG] get_chat_member failed: {e}, channel_id={cfg.channel_id}, user_id={user_id}")
            return False

    async def ensure_subscribed(call_or_msg, *, bot: Bot, user_id: int) -> bool:
        ok = await is_subscribed(bot, user_id)
        if ok:
            return True
        text = "Для записи необходимо подписаться на канал"
        kb = subscribe_required_kb(cfg.channel_link)
        if isinstance(call_or_msg, CallbackQuery):
            await call_or_msg.message.answer(text, reply_markup=kb)  
            try:
                await call_or_msg.answer()
            except TelegramBadRequest:
              
                pass
        else:
            await call_or_msg.answer(text, reply_markup=kb)
        return False

    def rng_today() -> CalendarRange:
        start = date.today()
        end = start + timedelta(days=MAX_DAYS_AHEAD)
        return CalendarRange(start=start, end=end)

    async def publish_schedule(bot: Bot, date_s: str) -> None:
        is_closed = await db.is_day_closed(date_s)
        if is_closed:
            await bot.send_message(chat_id=cfg.schedule_channel_id, text=f"⛔ <b>{date_s}</b> — день закрыт")
            return
        
        slots = await db.list_slots(date_s)
        bookings = await db.list_bookings_by_date(date_s)
        booked_by = {b.id: {"name": b.name, "service": b.service_name} for b in bookings}
        text = format_schedule(date_s, slots, booked_by, public=True)  
        await bot.send_message(chat_id=cfg.schedule_channel_id, text=text)

    

    @router.callback_query(MenuCB.filter(F.action == "menu"))
    async def menu_cb(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        is_admin = call.from_user.id == cfg.admin_id
        await call.message.answer("Выберите действие:", reply_markup=main_menu_kb(is_admin=is_admin)) 
        await call.answer()

    @router.callback_query(SubCB.filter(F.action == "check"))
    async def sub_check_cb(call: CallbackQuery, state: FSMContext) -> None:
        ok = await is_subscribed(call.bot, call.from_user.id)
        if not ok:
            try:
                await call.answer("Подписка не найдена. Подпишитесь и попробуйте ещё раз.", show_alert=True)
            except TelegramBadRequest:
               
                pass
            return
        try:
            await call.answer("✅ Подписка подтверждена!")
        except TelegramBadRequest:
       
            pass
        
        await open_booking_calendar(call=call, state=state)

    @router.callback_query(MenuCB.filter(F.action == "book"))
    async def book_entry_cb(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        ok = await ensure_subscribed(call, bot=call.bot, user_id=call.from_user.id)
        if not ok:
            return

        services = await db.list_services(active_only=True)
        if not services:
            await call.message.answer("Услуги временно недоступны. Попробуйте позже.", reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id))  # type: ignore[union-attr]
            await call.answer()
            return
        await state.set_state(BookingStates.choosing_service)
        await call.message.answer("📋 <b>Выберите услугу:</b>", reply_markup=services_kb(services))  
        await call.answer()

    @router.callback_query(MenuCB.filter(F.action == "my"))
    async def my_booking_cb(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        b = await db.get_user_active_booking(call.from_user.id)
        if not b:
            await call.message.answer("У вас нет активной записи.", reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id))  # type: ignore[union-attr]
            await call.answer()
            return
        text = (
            "📌 <b>Ваша запись</b>\n\n"
            f"Дата: <b>{esc(b.date)}</b>\n"
            f"Время: <b>{esc(b.time)}</b>\n"
            f"Имя: <b>{esc(b.name)}</b>\n"
            f"Телефон: <code>{esc(b.phone)}</code>\n\n"
            "Хотите отменить запись?"
        )
        await state.set_state(BookingStates.cancelling_confirm)
        await state.update_data(cancel_booking_id=b.id)
        await call.message.answer(text, reply_markup=cancel_confirm_kb())  # type: ignore[union-attr]
        await call.answer()

    # -------- service selection --------

    @router.callback_query(ServiceCB.filter())
    async def service_selected_cb(call: CallbackQuery, callback_data: ServiceCB, state: FSMContext) -> None:
        ok = await ensure_subscribed(call, bot=call.bot, user_id=call.from_user.id)
        if not ok:
            return

        service = await db.get_service(callback_data.service_id)
        if not service:
            await call.answer("Услуга не найдена.", show_alert=True)
            return

        await state.update_data(service_id=service["id"], service_name=service["name"])
        await open_booking_calendar(call=call, state=state)

    # -------- calendar / times --------

    async def open_booking_calendar(call: CallbackQuery, state: FSMContext | None) -> None:
        ok = await ensure_subscribed(call, bot=call.bot, user_id=call.from_user.id)
        if not ok:
            return

        rng = rng_today()
        start_s = rng.start.strftime(DATE_FMT)
        end_s = rng.end.strftime(DATE_FMT)
        available_dates = set(await db.list_available_dates(start_s, end_s))
        open_dates = set(await db.list_open_dates(start_s, end_s))

        if not available_dates:
            await call.message.answer("Пока нет доступных слотов. Попробуйте позже.", reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id))  # type: ignore[union-attr]
            await call.answer()
            return

        month = date(rng.start.year, rng.start.month, 1)
        cal_kb = build_calendar(
            scope="user",
            month=month,
            allowed_dates=available_dates,
            rng=rng,
            title="Выберите дату",
            open_dates=open_dates,
        )
        if state is not None:
            await state.set_state(BookingStates.choosing_date)
        await call.message.answer("🗓 <b>Выберите дату для записи</b>", reply_markup=cal_kb)  # type: ignore[union-attr]
        await call.answer()

    @router.callback_query(CalCB.filter(F.scope == "user"))
    async def calendar_user_cb(call: CallbackQuery, callback_data: CalCB, state: FSMContext) -> None:
        ok = await ensure_subscribed(call, bot=call.bot, user_id=call.from_user.id)
        if not ok:
            return

        rng = rng_today()
        start_s = rng.start.strftime(DATE_FMT)
        end_s = rng.end.strftime(DATE_FMT)
        available_dates = set(await db.list_available_dates(start_s, end_s))
        open_dates = set(await db.list_open_dates(start_s, end_s))

        # Навигация
        if callback_data.d == 0 and callback_data.nav in {"prev", "next"}:
            month = date(callback_data.y, callback_data.m, 1)
            cal_kb = build_calendar(
                scope="user",
                month=month,
                allowed_dates=available_dates,
                rng=rng,
                title="Выберите дату",
                open_dates=open_dates,
            )
            await call.message.edit_reply_markup(reply_markup=cal_kb)  # type: ignore[union-attr]
            await call.answer()
            return

        # Нажатие по "неактивным" — игнор
        if callback_data.d == 0:
            await call.answer()
            return

        selected = date(callback_data.y, callback_data.m, callback_data.d).strftime(DATE_FMT)
        if selected not in available_dates:
            await call.answer("Эта дата недоступна.", show_alert=True)
            return

        # Получаем service_id из состояния
        data = await state.get_data()
        service_id = data.get("service_id")
        
        free_times = await db.list_free_slots(selected, service_id)
        if not free_times:
            await call.answer("Свободных слотов нет.", show_alert=True)
            return

        await state.set_state(BookingStates.choosing_time)
        await state.update_data(date=selected)
        await call.message.answer(  # type: ignore[union-attr]
            f"🕒 <b>{esc(selected)}</b>\nВыберите время:",
            reply_markup=times_kb(selected, free_times),
        )
        await call.answer()

    @router.callback_query(TimeCB.filter())
    async def time_selected_cb(call: CallbackQuery, callback_data: TimeCB, state: FSMContext) -> None:
        ok = await ensure_subscribed(call, bot=call.bot, user_id=call.from_user.id)
        if not ok:
            return

        time_s = callback_data.unpack_time()  # Замена - обратно на :
        data = await state.get_data()
        service_id = data.get("service_id")
        free = await db.list_free_slots(callback_data.date, service_id)
        if time_s not in free:
            await call.answer("Этот слот уже занят. Выберите другое время.", show_alert=True)
            return

        await state.update_data(date=callback_data.date, time=time_s)
        await state.set_state(BookingStates.entering_name)
        await call.message.answer("Введите <b>имя</b>:")  # type: ignore[union-attr]
        await call.answer()

    # -------- FSM steps --------

    @router.message(BookingStates.entering_name)
    async def name_msg(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if len(name) < 2:
            await message.answer("Имя слишком короткое. Введите ещё раз:")
            return
        await state.update_data(name=name)
        await state.set_state(BookingStates.entering_phone)
        await message.answer("Введите <b>номер телефона</b>:")

    @router.message(BookingStates.entering_phone)
    async def phone_msg(message: Message, state: FSMContext) -> None:
        phone = (message.text or "").strip()
        if not re.fullmatch(r"[0-9+()\-\s]{6,25}", phone):
            await message.answer("Номер телефона выглядит некорректно. Введите ещё раз:")
            return
        data = await state.get_data()
        date_s = str(data.get("date", ""))
        time_s = str(data.get("time", ""))
        name = str(data.get("name", ""))
        service_name = str(data.get("service_name", ""))

        await state.update_data(phone=phone)
        await state.set_state(BookingStates.confirming)

        text = (
            "✅ <b>Подтвердите запись</b>\n\n"
            f"Услуга: <b>{esc(service_name)}</b>\n"
            f"Дата: <b>{esc(date_s)}</b>\n"
            f"Время: <b>{esc(time_s)}</b>\n"
            f"Имя: <b>{esc(name)}</b>\n"
            f"Телефон: <code>{esc(phone)}</code>"
        )
        await message.answer(text, reply_markup=confirm_booking_kb())

    @router.callback_query(BookingCB.filter(F.action == "cancel"))
    async def booking_cancel_cb(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await call.message.answer("Ок, отменено.", reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id))  # type: ignore[union-attr]
        await call.answer()

    @router.callback_query(BookingCB.filter(F.action == "confirm"))
    async def booking_confirm_cb(call: CallbackQuery, state: FSMContext) -> None:
        ok = await ensure_subscribed(call, bot=call.bot, user_id=call.from_user.id)
        if not ok:
            return

        data = await state.get_data()
        date_s = str(data.get("date", ""))
        time_s = str(data.get("time", ""))
        name = str(data.get("name", ""))
        phone = str(data.get("phone", ""))
        service_id = data.get("service_id")

        # финальная проверка: есть ли активная запись
        already = await db.get_user_active_booking(call.from_user.id)
        if already:
            await state.clear()
            await call.message.answer("У вас уже есть активная запись. Сначала отмените её.", reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id))  # type: ignore[union-attr]
            await call.answer()
            return

        created_at = tznow(cfg.timezone).replace(tzinfo=None)
        ok2, res = await db.create_booking(
            user_id=call.from_user.id,
            date=date_s,
            time=time_s,
            name=name,
            phone=phone,
            created_at=created_at,
            service_id=int(service_id) if service_id else None,
        )
        if not ok2:
            await call.message.answer(f"❌ {esc(str(res))}", reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id))  # type: ignore[union-attr]
            await state.clear()
            await call.answer()
            return

        booking: Booking = res  # type: ignore[assignment]
        service_name = data.get("service_name", "—")

        # Сообщение пользователю
        await call.message.answer(  # type: ignore[union-attr]
            "🎉 <b>Запись подтверждена!</b>\n\n"
            f"Услуга: <b>{esc(str(service_name))}</b>\n"
            f"Дата: <b>{esc(booking.date)}</b>\n"
            f"Время: <b>{esc(booking.time)}</b>\n"
            f"Имя: <b>{esc(booking.name)}</b>\n"
            f"Телефон: <code>{esc(booking.phone)}</code>",
            reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id),
        )

        # Сообщение админу
        u = call.from_user
        uname = f"@{u.username}" if u.username else "—"
        admin_text = (
            "🆕 <b>Новая запись</b>\n\n"
            f"Услуга: <b>{esc(str(service_name))}</b>\n"
            f"Дата: <b>{esc(booking.date)}</b>\n"
            f"Время: <b>{esc(booking.time)}</b>\n"
            f"Имя: <b>{esc(booking.name)}</b>\n"
            f"Телефон: <code>{esc(booking.phone)}</code>\n"
            f"Пользователь: <code>{u.id}</code> ({esc(uname)})"
        )
        await call.bot.send_message(chat_id=cfg.admin_id, text=admin_text)

        # Канал расписания
        await publish_schedule(call.bot, booking.date)
        await deps.reminders.plan_for_booking(booking)

        await state.clear()
        await call.answer()

    # -------- Cancel booking (FSM) --------

    @router.callback_query(BookingCB.filter(F.action == "confirm_cancel"))
    async def cancel_confirm_cb(call: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        booking_id = int(data.get("cancel_booking_id", 0) or 0)
        b = await db.get_booking(booking_id)
        if not b or b.user_id != call.from_user.id or b.status != "active":
            await state.clear()
            await call.message.answer("Запись не найдена.", reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id))  # type: ignore[union-attr]
            await call.answer()
            return

        cancelled = await db.cancel_booking_by_id(booking_id)
        if not cancelled:
            await state.clear()
            await call.message.answer("Не удалось отменить запись.", reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id))  # type: ignore[union-attr]
            await call.answer()
            return

        # удаляем напоминание
        await deps.reminders.delete_for_booking(b)

        await call.message.answer(  # type: ignore[union-attr]
            "✅ Запись отменена. Слот снова доступен.",
            reply_markup=main_menu_kb(is_admin=call.from_user.id == cfg.admin_id),
        )

        await call.bot.send_message(
            chat_id=cfg.admin_id,
            text=(
                "❌ <b>Отмена записи</b>\n\n"
                f"Дата: <b>{esc(b.date)}</b>\n"
                f"Время: <b>{esc(b.time)}</b>\n"
                f"Имя: <b>{esc(b.name)}</b>\n"
                f"Телефон: <code>{esc(b.phone)}</code>"
            ),
        )

        await publish_schedule(call.bot, b.date)

        await state.clear()
        await call.answer()

    return router

