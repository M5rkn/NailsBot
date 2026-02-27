from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.constants import DATE_FMT, MAX_DAYS_AHEAD
from app.db.sqlite import Database
from app.fsm.states import AdminStates
from app.keyboards.admin import AdminCB, AdminServiceCB, AdminTimeCB, admin_existing_slots_kb, admin_menu_kb, admin_times_grid, services_admin_kb
from app.keyboards.calendar import CalendarRange, CalCB, build_calendar
from app.keyboards.common import MenuCB
from app.scheduler.reminders import ReminderScheduler
from app.utils.format import esc, format_schedule


@dataclass(slots=True)
class AdminDeps:
    cfg: object
    db: Database
    reminders: ReminderScheduler


def get_router(*, cfg, db: Database, reminders: ReminderScheduler) -> Router:
    router = Router()
    deps = AdminDeps(cfg=cfg, db=db, reminders=reminders)

    def is_admin(user_id: int) -> bool:
        return user_id == cfg.admin_id

    def rng_today() -> CalendarRange:
        start = date.today()
        end = start + timedelta(days=MAX_DAYS_AHEAD)
        return CalendarRange(start=start, end=end)

    def all_dates_in_range(rng: CalendarRange) -> set[str]:
        d = rng.start
        out: set[str] = set()
        while d <= rng.end:
            out.add(d.strftime(DATE_FMT))
            d += timedelta(days=1)
        return out

    async def publish_schedule(call: CallbackQuery, date_s: str) -> None:
        is_closed = await db.is_day_closed(date_s)
        if is_closed:
            await call.bot.send_message(chat_id=cfg.schedule_channel_id, text=f"⛔ <b>{date_s}</b> — день закрыт")
            return
        
        slots = await db.list_slots(date_s)
        bookings = await db.list_bookings_by_date(date_s)
        booked_by = {b.id: {"name": b.name, "service": b.service_name} for b in bookings}
        text = format_schedule(date_s, slots, booked_by, public=True)  # Публичная версия без имён
        await call.bot.send_message(chat_id=cfg.schedule_channel_id, text=text)

    

    @router.callback_query(MenuCB.filter(F.action == "admin"))
    async def admin_entry(call: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer("Нет доступа.", show_alert=True)
            return
        await state.clear()
        await state.set_state(AdminStates.choosing_action)
        await call.message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_menu_kb())  # type: ignore[union-attr]
        await call.answer()

    @router.callback_query(AdminCB.filter(F.action == "menu"))
    async def admin_menu(call: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer("Нет доступа.", show_alert=True)
            return
        await state.clear()
        await state.set_state(AdminStates.choosing_action)
        await call.message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_menu_kb())  # type: ignore[union-attr]
        await call.answer()

    

    @router.callback_query(AdminCB.filter(F.action != "menu"))
    async def admin_action(call: CallbackQuery, callback_data: AdminCB, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer("Нет доступа.", show_alert=True)
            return
        action = callback_data.action

        rng = rng_today()
        
        
        admin_rng = CalendarRange(
            start=date.today().replace(day=1), 
            end=rng.end
        )

      
        start_s = rng.start.strftime(DATE_FMT)
        end_s = rng.end.strftime(DATE_FMT)
        dates_with_slots = set(await db.list_dates_with_slots(start_s, end_s))
        allowed = set(await db.list_available_dates(start_s, end_s))
        open_dates = set(await db.list_open_dates(start_s, end_s))

       
        cur = await db.conn.execute(
            "SELECT date FROM working_days WHERE date BETWEEN ? AND ? AND is_closed = 1;",
            (start_s, end_s),
        )
        rows = await cur.fetchall()
        closed_dates = {r["date"] for r in rows}

        if action == "add_day":
         
            allowed = all_dates_in_range(admin_rng)
            dates_with_slots = None
            closed_dates = set()
            open_dates = set()
        elif action == "open_day":
            
            allowed = closed_dates  
            dates_with_slots = None
        elif action == "close_day":
           
            allowed = open_dates
            dates_with_slots = None
        elif action == "view":
           
            pass
        

        month = date(rng.start.year, rng.start.month, 1)

        await state.set_state(AdminStates.choosing_date)
        await state.update_data(admin_action=action)
        cal_kb = build_calendar(scope="admin", month=month, allowed_dates=allowed, rng=admin_rng, title="Выберите дату", dates_with_slots=dates_with_slots, closed_dates=closed_dates, open_dates=open_dates)

        title_map = {
            "add_day": "➕ Добавить рабочий день",
            "close_day": "⛔ Закрыть день",
            "open_day": "✅ Открыть день",
            "add_slot": "🕒 Добавить слот",
            "del_slot": "🗑 Удалить слот",
            "cancel_booking": "❌ Отменить запись",
            "view": "📅 Просмотр расписания",
            "services": "📋 Управление услугами",
        }
        title = title_map.get(action, "Выберите дату")
        
       
        if action == "services":
            services = await db.list_services(active_only=False)
            await call.message.answer("<b>📋 Услуги</b>\n\nНажмите на услугу, чтобы включить/выключить её:", reply_markup=services_admin_kb(services))  # type: ignore[union-attr]
            await call.answer()
            return
        
        await state.set_state(AdminStates.choosing_date)
        await state.update_data(admin_action=action)
        cal_kb = build_calendar(scope="admin", month=month, allowed_dates=allowed, rng=rng, title="Выберите дату", dates_with_slots=dates_with_slots, closed_dates=closed_dates, open_dates=open_dates)
        await call.message.answer(f"<b>{esc(title)}</b>\nВыберите дату:", reply_markup=cal_kb)  # type: ignore[union-attr]
        await call.answer()



    @router.callback_query(CalCB.filter(F.scope == "admin"))
    async def calendar_admin_cb(call: CallbackQuery, callback_data: CalCB, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer("Нет доступа.", show_alert=True)
            return

        rng = rng_today()
        
        admin_rng = CalendarRange(
            start=date.today().replace(day=1),  
            end=rng.end
        )
        data = await state.get_data()
        action = str(data.get("admin_action", ""))

       
        start_s = rng.start.strftime(DATE_FMT)
        end_s = rng.end.strftime(DATE_FMT)
        dates_with_slots = set(await db.list_dates_with_slots(start_s, end_s))
        allowed = set(await db.list_available_dates(start_s, end_s))
        open_dates = set(await db.list_open_dates(start_s, end_s))

      
        cur = await db.conn.execute(
            "SELECT date FROM working_days WHERE date BETWEEN ? AND ? AND is_closed = 1;",
            (start_s, end_s),
        )
        rows = await cur.fetchall()
        closed_dates = {r["date"] for r in rows}

        if action == "add_day":
            
            allowed = all_dates_in_range(admin_rng)
            dates_with_slots = None
            closed_dates = set()
            open_dates = set()
        elif action == "open_day":
           
            allowed = closed_dates
            dates_with_slots = None
        elif action == "close_day":
          
            allowed = open_dates
            dates_with_slots = None
        elif action == "view":
           
            pass
       

        if callback_data.d == 0 and callback_data.nav in {"prev", "next"}:
            
            start_s = rng.start.strftime(DATE_FMT)
            end_s = rng.end.strftime(DATE_FMT)

            if action == "add_day":
                allowed = all_dates_in_range(admin_rng)
                dates_with_slots = None
                closed_dates = set()
                open_dates = set()
            elif action == "view":
                dates_with_slots = set(await db.list_dates_with_slots(start_s, end_s))
                allowed = set(await db.list_available_dates(start_s, end_s))
                open_dates = set(await db.list_open_dates(start_s, end_s))
                cur = await db.conn.execute(
                    "SELECT date FROM working_days WHERE date BETWEEN ? AND ? AND is_closed = 1;",
                    (start_s, end_s),
                )
                rows = await cur.fetchall()
                closed_dates = {r["date"] for r in rows}
            elif action == "open_day":
               
                cur = await db.conn.execute(
                    "SELECT date FROM working_days WHERE date BETWEEN ? AND ? AND is_closed = 1;",
                    (start_s, end_s),
                )
                rows = await cur.fetchall()
                closed_dates = {r["date"] for r in rows}
                allowed = closed_dates
                dates_with_slots = None
            elif action == "close_day":
                
                allowed = set(await db.list_open_dates(start_s, end_s))
                dates_with_slots = None
                cur = await db.conn.execute(
                    "SELECT date FROM working_days WHERE date BETWEEN ? AND ? AND is_closed = 1;",
                    (start_s, end_s),
                )
                rows = await cur.fetchall()
                closed_dates = {r["date"] for r in rows}
            else:
                allowed = set(await db.list_available_dates(start_s, end_s))
                open_dates = set(await db.list_open_dates(start_s, end_s))
                dates_with_slots = None
                cur = await db.conn.execute(
                    "SELECT date FROM working_days WHERE date BETWEEN ? AND ? AND is_closed = 1;",
                    (start_s, end_s),
                )
                rows = await cur.fetchall()
                closed_dates = {r["date"] for r in rows}

            month = date(callback_data.y, callback_data.m, 1)
            cal_kb = build_calendar(scope="admin", month=month, allowed_dates=allowed, rng=admin_rng, title="Выберите дату", dates_with_slots=dates_with_slots, closed_dates=closed_dates, open_dates=open_dates)
            await call.message.edit_reply_markup(reply_markup=cal_kb)  
            await call.answer()
            return

        if callback_data.d == 0:
            await call.answer()
            return

        selected = date(callback_data.y, callback_data.m, callback_data.d).strftime(DATE_FMT)

    
        if action == "open_day":
            await db.set_day_closed(selected, False)
            await call.message.answer(f"✅ День открыт: <b>{esc(selected)}</b>", reply_markup=admin_menu_kb())  
            await publish_schedule(call, selected)
            await state.set_state(AdminStates.choosing_action)
            await call.answer()
            return

        if action == "close_day":
            await db.set_day_closed(selected, True)
            await call.message.answer(f"⛔ День закрыт: <b>{esc(selected)}</b>", reply_markup=admin_menu_kb()) 
            await publish_schedule(call, selected)
            await state.set_state(AdminStates.choosing_action)
            await call.answer()
            return

        if action == "add_day":
            await db.add_working_day(selected, auto_add_slots=True)
            await call.message.answer(f"✅ Рабочий день добавлен: <b>{esc(selected)}</b>", reply_markup=admin_menu_kb())  
            await state.set_state(AdminStates.choosing_action)
            await call.answer()
            return

        if action == "add_slot":
            await state.update_data(date=selected)
            await state.set_state(AdminStates.choosing_time)
            await call.message.answer(f"Выберите время для <b>{esc(selected)}</b>:", reply_markup=admin_times_grid(selected, mode="add")) 
            await call.answer()
            return

        if action == "del_slot":
            slots = await db.list_slots(selected)
            free_times = [s["time"] for s in slots if int(s["is_booked"]) == 0]
            if not free_times:
                await call.message.answer("Нет свободных слотов для удаления.", reply_markup=admin_menu_kb())  
                await state.set_state(AdminStates.choosing_action)
                await call.answer()
                return
            await state.update_data(date=selected)
            await state.set_state(AdminStates.choosing_time)
            await call.message.answer(
                f"Выберите слот для удаления (<b>{esc(selected)}</b>):",
                reply_markup=admin_existing_slots_kb(selected, free_times, mode="del"),
            ) 
            await call.answer()
            return

        if action == "cancel_booking":
           
            bookings = await db.list_bookings_by_date(selected)
            if not bookings:
                await call.message.answer("На эту дату нет записей.", reply_markup=admin_menu_kb())  
                await state.set_state(AdminStates.choosing_action)
                await call.answer()
                return
            
           
            booking_times = [b.time for b in bookings]
            await state.update_data(date=selected)
            await state.set_state(AdminStates.choosing_time)
            await call.message.answer(
                f"Выберите запись для отмены (<b>{esc(selected)}</b>):",
                reply_markup=admin_existing_slots_kb(selected, booking_times, mode="cancel"),
            ) 
            await call.answer()
            return

        if action == "view":
            is_closed = await db.is_day_closed(selected)
            if is_closed:
                await call.message.answer(f"⛔ <b>{esc(selected)}</b> — день закрыт", reply_markup=admin_menu_kb())  
                await state.set_state(AdminStates.choosing_action)
                await call.answer()
                return
            
            slots = await db.list_slots(selected)
            bookings = await db.list_bookings_by_date(selected)
            booked_by = {b.id: {"name": b.name, "service": b.service_name} for b in bookings}
            text = format_schedule(selected, slots, booked_by, public=False)  
            await call.message.answer(text, reply_markup=admin_menu_kb())  
            await state.set_state(AdminStates.choosing_action)
            await call.answer()
            return

        await call.answer("Неизвестное действие.", show_alert=True)

  

    @router.callback_query(AdminTimeCB.filter())
    async def admin_time_cb(call: CallbackQuery, callback_data: AdminTimeCB, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer("Нет доступа.", show_alert=True)
            return

        date_s = callback_data.date
        time_s = callback_data.unpack_time() 
        mode = callback_data.mode

        if mode == "add":
            ok = await db.add_slot(date_s, time_s)
            if ok:
                await call.message.answer(f"✅ Слот добавлен: <b>{esc(date_s)}</b> <b>{esc(time_s)}</b>", reply_markup=admin_menu_kb())  
                await publish_schedule(call, date_s)
            else:
                await call.message.answer("Не удалось добавить слот (день закрыт или слот уже есть).", reply_markup=admin_menu_kb())  
            await state.set_state(AdminStates.choosing_action)
            await call.answer()
            return

        if mode == "del":
            ok = await db.delete_slot(date_s, time_s)
            if ok:
                await call.message.answer(f"🗑 Слот удалён: <b>{esc(date_s)}</b> <b>{esc(time_s)}</b>", reply_markup=admin_menu_kb())  
                await publish_schedule(call, date_s)
            else:
                await call.message.answer("Не удалось удалить (возможно слот занят).", reply_markup=admin_menu_kb())  
            await state.set_state(AdminStates.choosing_action)
            await call.answer()
            return

        if mode == "cancel":
            booking = await db.get_booking_by_slot(date_s, time_s)
            if not booking:
                await call.message.answer("Запись не найдена.", reply_markup=admin_menu_kb())  
                await state.set_state(AdminStates.choosing_action)
                await call.answer()
                return

            cancelled = await db.cancel_booking_by_id(booking.id)
            if not cancelled:
                await call.message.answer("Не удалось отменить запись.", reply_markup=admin_menu_kb()) 
                await state.set_state(AdminStates.choosing_action)
                await call.answer()
                return

            await deps.reminders.delete_for_booking(booking)

            
            await call.bot.send_message(
                chat_id=booking.user_id,
                text=(
                    "❌ <b>Ваша запись отменена администратором</b>\n\n"
                    f"Дата: <b>{esc(booking.date)}</b>\n"
                    f"Время: <b>{esc(booking.time)}</b>"
                ),
            )
            await call.message.answer("✅ Запись отменена, слот освобождён.", reply_markup=admin_menu_kb())  
            await publish_schedule(call, date_s)
            await state.set_state(AdminStates.choosing_action)
            await call.answer()
            return

        await call.answer("Неизвестный режим.", show_alert=True)

   

    @router.callback_query(AdminServiceCB.filter())
    async def service_toggle_cb(call: CallbackQuery, callback_data: AdminServiceCB, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer("Нет доступа.", show_alert=True)
            return

        service = await db.get_service(callback_data.service_id)
        if not service:
            await call.answer("Услуга не найдена.", show_alert=True)
            return

        
        new_status = not service["is_active"]
        await db.toggle_service(callback_data.service_id, new_status)

       
        services = await db.list_services(active_only=False)
        await call.message.edit_reply_markup(reply_markup=services_admin_kb(services))  
        await call.answer(f"Услуга '{service['name']}' {'включена' if new_status else 'выключена'}")

    return router

