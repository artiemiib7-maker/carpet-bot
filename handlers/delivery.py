import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import sheets
from config import DRIVER_PHONES, CITY_GROUPS, RESCHEDULE_FEE, TEXTS
from keyboards import (
    reschedule_dates_kb, ready_dates_kb, ready_hours_kb, ready_minutes_kb,
)
from states import RescheduleForm

router = Router()


def _driver_phone(city_name: str) -> str:
    for code, name in CITY_GROUPS.items():
        if name == city_name:
            return DRIVER_PHONES[code]
    return next(iter(DRIVER_PHONES.values()))


@router.callback_query(F.data.startswith("ready:"))
async def ready_to_accept(callback: CallbackQuery):
    order_id = int(callback.data.split(":", 1)[1])
    await callback.message.edit_text(
        callback.message.text + "\n\n" + TEXTS["delivery_confirmed"]
    )
    await callback.answer()


@router.callback_query(F.data.startswith("driver:"))
async def contact_driver(callback: CallbackQuery):
    order_id = int(callback.data.split(":", 1)[1])
    order = await asyncio.to_thread(sheets.get_order, order_id)
    city = str(order.get("город", "")) if order else ""
    phone = _driver_phone(city)
    await callback.message.answer(TEXTS["driver_contact"].format(phone=phone))
    await callback.answer()


@router.callback_query(F.data.startswith("resched:"))
async def reschedule_start(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":", 1)[1])
    order = await asyncio.to_thread(sheets.get_order, order_id)
    if not order:
        await callback.answer("Не удалось найти заказ. Попробуйте позже.", show_alert=True)
        return
    await state.set_state(RescheduleForm.delivery_date)
    await state.update_data(order_id=order_id)
    await callback.message.answer(
        f"На какую дату перенести доставку? Доплата: +{RESCHEDULE_FEE} ₽.",
        reply_markup=reschedule_dates_kb(order_id, str(order.get("дата_доставки"))),
    )
    await callback.answer()


@router.callback_query(RescheduleForm.delivery_date, F.data.startswith("newdate:"))
async def reschedule_done(callback: CallbackQuery, state: FSMContext):
    _, order_id_s, new_date = callback.data.split(":")
    order_id = int(order_id_s)
    ok = await asyncio.to_thread(sheets.reschedule, order_id, new_date, RESCHEDULE_FEE)
    await state.clear()
    if ok:
        await callback.message.edit_text(
            TEXTS["rescheduled"].format(date=new_date)
        )
    else:
        await callback.message.edit_text(
            "Не удалось перенести доставку автоматически. "
            "Позвоните водителю — кнопка «📞 Связаться с водителем»."
        )
    await callback.answer()


# --- Выбор даты и времени доставки готового ковра ---
# Все данные зашиты в callback-кнопки (order_id, дата, час) — FSM не нужен,
# поэтому кнопки работают из любого сообщения, в т.ч. отправленного скриптом таблицы.


@router.callback_query(F.data.startswith("pickdate:"))
async def choose_delivery_date_start(callback: CallbackQuery):
    """Точка входа из «Мои заказы»: ковёр упакован, дата ещё не выбрана."""
    order_id = int(callback.data.split(":", 1)[1])
    await callback.message.answer(
        f"Заказ №{order_id}: {TEXTS['ready_for_delivery']}",
        reply_markup=ready_dates_kb(order_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rdate:"))
async def delivery_date_chosen(callback: CallbackQuery):
    _, order_id_s, date_iso = callback.data.split(":")
    order_id = int(order_id_s)
    await callback.message.edit_text(f"Дата доставки: {date_iso}")
    await callback.message.answer(
        TEXTS["ask_delivery_hour"], reply_markup=ready_hours_kb(order_id, date_iso)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rhour:"))
async def delivery_hour_chosen(callback: CallbackQuery):
    _, order_id_s, date_iso, hour_s = callback.data.split(":")
    order_id = int(order_id_s)
    hour = int(hour_s)
    await callback.message.edit_reply_markup(
        reply_markup=ready_minutes_kb(order_id, date_iso, hour)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rmin:"))
async def delivery_minute_chosen(callback: CallbackQuery):
    _, order_id_s, date_iso, hour_s, minute_s = callback.data.split(":")
    order_id = int(order_id_s)
    time_str = f"{hour_s}:{minute_s}"
    ok = await asyncio.to_thread(sheets.set_delivery, order_id, date_iso, time_str)
    if ok:
        await callback.message.edit_text(
            TEXTS["delivery_set"].format(date=date_iso, time=time_str)
        )
    else:
        await callback.message.edit_text(
            "Не удалось сохранить дату автоматически. "
            "Позвоните водителю — кнопка «📞 Связаться с водителем»."
        )
    await callback.answer()
