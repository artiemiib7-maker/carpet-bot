import asyncio
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import sheets
from config import CITY_GROUPS, PILE_TARIFFS, EXTRA_SERVICES, EXTRA_SHORT, TEXTS
from keyboards import (
    cancel_kb, back_kb, city_kb, address_city_kb, pile_kb, area_type_kb,
    extras_kb, pickup_dates_kb, confirm_kb, main_menu_kb,
)
from states import OrderForm

router = Router()

PHONE_RE = re.compile(r"[+\d][\d\s()\-]{8,}")


def _order_summary(data: dict) -> str:
    extras_names = [
        EXTRA_SERVICES[c][0] for c in data.get("extras", []) if c in EXTRA_SERVICES
    ]
    approx = data.get("area_approx") == "да"
    area_text = f"~{data['area']:g} кв.м (примерная)" if approx else f"{data['area']:g} кв.м"
    lines = [
        "🧾 <b>Итог заказа</b>",
        "",
        f"Маршрут: {data['route']}",
        f"Город: {data['city']}",
        f"Имя: {data['name']}",
        f"Телефон: {data['phone']}",
        f"Адрес забора: {data['address']}",
        f"Ворс: {data['pile_name']} — {data['tariff']} ₽/кв.м",
        f"Площадь: {area_text}",
        f"Базовая стирка: {data['base_total']:g} ₽",
    ]
    if extras_names:
        lines.append(f"Допуслуги: {', '.join(extras_names)} — {data['extras_total']:g} ₽")
    else:
        lines.append("Допуслуги: нет")
    lines.append(f"Дата забора: {data['pickup_date']}")
    lines.append("")
    if approx:
        lines.append(f"<b>Примерная стоимость: {data['total']:g} ₽</b>")
        lines.append(TEXTS["approx_note"])
    else:
        lines.append(f"<b>Итого: {data['total']:g} ₽</b>")
    return "\n".join(lines)


async def _prompt_step(message: Message, state: FSMContext, step: str) -> None:
    """Показывает приглашение указанного шага (используется и кнопкой «Назад»)."""
    data = await state.get_data()
    if step == "menu":
        await state.clear()
        await message.answer("Вы в главном меню.", reply_markup=main_menu_kb())
    elif step == "city":
        await state.set_state(OrderForm.city)
        await message.answer(TEXTS["ask_city"], reply_markup=city_kb())
    elif step == "name":
        await state.set_state(OrderForm.name)
        await message.answer(TEXTS["ask_name"], reply_markup=back_kb("address_city"))
    elif step == "phone":
        await state.set_state(OrderForm.phone)
        await message.answer(TEXTS["ask_phone"], reply_markup=back_kb("name"))
    elif step == "address_city":
        await state.set_state(OrderForm.address_city)
        await message.answer(
            TEXTS["ask_address_city"],
            reply_markup=address_city_kb(data["route_code"]),
        )
    elif step == "street":
        await state.set_state(OrderForm.street)
        await message.answer(TEXTS["ask_street"], reply_markup=back_kb("address_city"))
    elif step == "house":
        await state.set_state(OrderForm.house)
        await message.answer(TEXTS["ask_house"], reply_markup=back_kb("street"))
    elif step == "apartment":
        await state.set_state(OrderForm.apartment)
        await message.answer(TEXTS["ask_apartment"], reply_markup=back_kb("house"))
    elif step == "pile":
        await state.set_state(OrderForm.pile)
        await message.answer(TEXTS["ask_pile"], reply_markup=pile_kb())
    elif step == "area_type":
        await state.set_state(OrderForm.area_type)
        await message.answer(TEXTS["ask_area_type"], reply_markup=area_type_kb())
    elif step == "area":
        await state.set_state(OrderForm.area)
        await message.answer(TEXTS["ask_area"], reply_markup=back_kb("area_type"))
    elif step == "extras":
        await state.set_state(OrderForm.extras)
        selected = set(data.get("extras", []))
        await message.answer(TEXTS["ask_extras"], reply_markup=extras_kb(selected))
    elif step == "pickup_date":
        await state.set_state(OrderForm.pickup_date)
        await message.answer(TEXTS["ask_pickup_date"], reply_markup=pickup_dates_kb())


@router.callback_query(F.data.startswith("back:"))
async def go_back(callback: CallbackQuery, state: FSMContext):
    step = callback.data.split(":", 1)[1]
    await _prompt_step(callback.message, state, step)
    await callback.answer()


@router.message(F.text == "🧺 Оформить заказ")
async def start_order(message: Message, state: FSMContext):
    await message.answer("Для отмены нажмите «❌ Отмена»", reply_markup=cancel_kb())
    await _prompt_step(message, state, "city")


@router.callback_query(OrderForm.city, F.data.startswith("city:"))
async def got_city(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    if code not in CITY_GROUPS:
        await callback.answer()
        return
    route_name = CITY_GROUPS[code][0]
    await state.update_data(route=route_name, route_code=code)
    await callback.message.edit_text(f"Маршрут: {route_name}")
    await _prompt_step(callback.message, state, "address_city")
    await callback.answer()


@router.message(OrderForm.name)
async def got_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Введите имя (минимум 2 символа):")
        return
    await state.update_data(name=name)
    await _prompt_step(message, state, "phone")


@router.message(OrderForm.phone)
async def got_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    digits = re.sub(r"\D", "", phone)
    if not PHONE_RE.fullmatch(phone) or len(digits) < 10:
        await message.answer(TEXTS["bad_phone"])
        return
    await state.update_data(phone=phone)
    await _prompt_step(message, state, "street")


@router.callback_query(OrderForm.address_city, F.data.startswith("acity:"))
async def got_address_city(callback: CallbackQuery, state: FSMContext):
    city = callback.data.split(":", 1)[1]
    await state.update_data(city=city)
    await callback.message.edit_text(f"Город: {city}")
    await _prompt_step(callback.message, state, "name")
    await callback.answer()


@router.message(OrderForm.street)
async def got_street(message: Message, state: FSMContext):
    street = message.text.strip()
    if len(street) < 2:
        await message.answer("Введите улицу:")
        return
    await state.update_data(street=street)
    await _prompt_step(message, state, "house")


@router.message(OrderForm.house)
async def got_house(message: Message, state: FSMContext):
    house = message.text.strip()
    if not house:
        await message.answer("Введите номер дома:")
        return
    await state.update_data(house=house)
    await _prompt_step(message, state, "apartment")


@router.message(OrderForm.apartment)
async def got_apartment(message: Message, state: FSMContext):
    apartment = message.text.strip()
    if not apartment:
        await message.answer("Введите номер квартиры:")
        return
    data = await state.get_data()
    address = f"ул. {data['street']}, д. {data['house']}, кв. {apartment}"
    await state.update_data(apartment=apartment, address=address)
    await _prompt_step(message, state, "pile")


@router.callback_query(OrderForm.pile, F.data.startswith("pile:"))
async def got_pile(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    if code not in PILE_TARIFFS:
        await callback.answer()
        return
    pile_name, tariff = PILE_TARIFFS[code]
    await state.update_data(pile_name=pile_name, tariff=tariff)
    await callback.message.edit_text(f"Ворс: {pile_name} — {tariff} ₽/кв.м")
    await _prompt_step(callback.message, state, "area_type")
    await callback.answer()


@router.callback_query(OrderForm.area_type, F.data.startswith("atype:"))
async def got_area_type(callback: CallbackQuery, state: FSMContext):
    kind = callback.data.split(":", 1)[1]
    approx = "да" if kind == "approx" else "нет"
    await state.update_data(area_approx=approx)
    await callback.message.edit_text(
        "Площадь примерная — посчитаем ориентировочно."
        if kind == "approx" else "Хорошо, введите точную площадь."
    )
    await _prompt_step(callback.message, state, "area")
    await callback.answer()


@router.message(OrderForm.area)
async def got_area(message: Message, state: FSMContext):
    try:
        area = float(message.text.replace(",", ".").strip())
        if not (0.1 <= area <= 1000):
            raise ValueError
    except ValueError:
        await message.answer(TEXTS["bad_area"])
        return
    await state.update_data(area=area, extras=[])
    await _prompt_step(message, state, "extras")


@router.callback_query(OrderForm.extras, F.data.startswith("extra:"))
async def got_extra(callback: CallbackQuery, state: FSMContext):
    code = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = set(data.get("extras", []))

    if code in ("done", "skip"):
        if code == "skip":
            selected = set()
        await state.update_data(extras=sorted(selected))
        await callback.message.edit_text("Допуслуги выбраны." if selected else "Без допуслуг.")
        await _prompt_step(callback.message, state, "pickup_date")
    elif code in EXTRA_SERVICES:
        if code in selected:
            selected.discard(code)
        else:
            selected.add(code)
        await state.update_data(extras=sorted(selected))
        await callback.message.edit_reply_markup(reply_markup=extras_kb(selected))
    await callback.answer()


@router.callback_query(OrderForm.pickup_date, F.data.startswith("pickup:"))
async def got_pickup(callback: CallbackQuery, state: FSMContext):
    pickup_iso = callback.data.split(":", 1)[1]
    await state.update_data(pickup_date=pickup_iso)
    data = await state.get_data()

    area = data["area"]
    tariff = data["tariff"]
    base_total = tariff * area
    extras_total = sum(EXTRA_SERVICES[c][1] for c in data.get("extras", [])) * area
    total = base_total + extras_total
    await state.update_data(
        base_total=base_total, extras_total=extras_total, total=total,
    )

    data = await state.get_data()
    await state.set_state(OrderForm.confirm)
    await callback.message.edit_text(f"Дата забора: {pickup_iso}")
    await callback.message.answer(
        _order_summary(data), parse_mode="HTML", reply_markup=confirm_kb()
    )
    await callback.answer()


@router.callback_query(OrderForm.confirm, F.data.startswith("confirm:"))
async def got_confirm(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action == "no":
        await state.clear()
        await callback.message.edit_text("Заказ отменён.")
        await callback.message.answer("Вы в главном меню.", reply_markup=main_menu_kb())
        return

    data = await state.get_data()
    order = {
        "telegram_id": callback.from_user.id,
        "username": callback.from_user.username or "",
        "name": data["name"],
        "phone": data["phone"],
        "route": data["route"],
        "city": data["city"],
        "address": data["address"],
        "pile": data["pile_name"],
        "area": data["area"],
        "area_approx": data.get("area_approx", "нет"),
        "extras": ", ".join(
            EXTRA_SHORT[c] for c in data.get("extras", []) if c in EXTRA_SHORT
        ) or "нет",
        "tariff": data["tariff"],
        "extras_total": data["extras_total"],
        "total": data["total"],
        "pickup_date": data["pickup_date"],
    }
    order_id = await asyncio.to_thread(sheets.add_order, order)
    await state.clear()
    if order_id is not None:
        await callback.message.edit_text(
            f"✅ Заказ №{order_id} принят!\n\n"
            "Мы заберём ковёр в указанную дату. Когда ковёр будет готов, "
            "я предложу выбрать дату и время доставки."
        )
    else:
        await callback.message.edit_text(
            "✅ Заказ принят! Номер будет назначен после синхронизации с таблицей.\n\n"
            "Статус можно смотреть в «📋 Мои заказы»."
        )
    await callback.message.answer("Вы в главном меню.", reply_markup=main_menu_kb())
