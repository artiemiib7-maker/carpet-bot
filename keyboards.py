from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import CITY_GROUPS, PILE_TARIFFS, EXTRA_SERVICES, RU_WEEKDAYS


def _back_row(target: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="◀ Назад", callback_data=f"back:{target}")]


def back_kb(target: str) -> InlineKeyboardMarkup:
    """Клавиатура только с кнопкой «Назад» — для текстовых шагов."""
    return InlineKeyboardMarkup(inline_keyboard=[_back_row(target)])


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧺 Оформить заказ")],
            [KeyboardButton(text="📋 Мои заказы")],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def city_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, (name, _cities) in CITY_GROUPS.items():
        builder.button(text=name, callback_data=f"city:{code}")
    builder.adjust(1)
    kb = builder.as_markup()
    kb.inline_keyboard.append(_back_row("menu"))
    return kb


def address_city_kb(group_code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for city in CITY_GROUPS[group_code][1]:
        builder.button(text=city, callback_data=f"acity:{city}")
    builder.adjust(1)
    kb = builder.as_markup()
    kb.inline_keyboard.append(_back_row("city"))
    return kb


def pile_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, (name, price) in PILE_TARIFFS.items():
        builder.button(text=f"{name} — {price} ₽/кв.м", callback_data=f"pile:{code}")
    builder.adjust(1)
    kb = builder.as_markup()
    kb.inline_keyboard.append(_back_row("apartment"))
    return kb


def area_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📏 Знаю точную площадь", callback_data="atype:exact")],
        [InlineKeyboardButton(text="📐 Примерно (нет рулетки)", callback_data="atype:approx")],
        _back_row("pile"),
    ])


def extras_kb(selected: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, (name, price) in EXTRA_SERVICES.items():
        mark = "✅ " if code in selected else ""
        builder.button(text=f"{mark}{name} — {price} ₽/кв.м", callback_data=f"extra:{code}")
    builder.button(text="✔ Готово", callback_data="extra:done")
    builder.button(text="⏭ Пропустить", callback_data="extra:skip")
    builder.adjust(1)
    kb = builder.as_markup()
    kb.inline_keyboard.append(_back_row("area"))
    return kb


def _fmt_date(d: date) -> str:
    return f"{d.strftime('%d.%m')} ({RU_WEEKDAYS[d.weekday()]})"


def pickup_dates_kb(days_ahead: int = 14) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    today = date.today()
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        builder.button(text=_fmt_date(d), callback_data=f"pickup:{d.isoformat()}")
    builder.adjust(3)
    kb = builder.as_markup()
    kb.inline_keyboard.append(_back_row("extras"))
    return kb


def _add_workdays(start: date, workdays: int) -> date:
    """Прибавляет N рабочих дней (без сб/вс) к дате."""
    d = start
    added = 0
    while added < workdays:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить заказ", callback_data="confirm:yes")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="confirm:no")],
        _back_row("pickup_date"),
    ])


def delivery_notice_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готов принять", callback_data=f"ready:{order_id}")
    builder.button(text="📅 Перенести (+100 ₽)", callback_data=f"resched:{order_id}")
    builder.button(text="📞 Связаться с водителем", callback_data=f"driver:{order_id}")
    builder.adjust(1)
    return builder.as_markup()


def reschedule_dates_kb(order_id: int, from_date_iso: str) -> InlineKeyboardMarkup:
    from_date = date.fromisoformat(from_date_iso)
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        d = _add_workdays(from_date, i)
        builder.button(
            text=f"{d.strftime('%d.%m.%Y')} ({RU_WEEKDAYS[d.weekday()]})",
            callback_data=f"newdate:{order_id}:{d.isoformat()}",
        )
    builder.adjust(2)
    return builder.as_markup()


def ready_dates_kb(order_id: int, days_ahead: int = 14) -> InlineKeyboardMarkup:
    """Даты получения готового ковра (после статуса «упакован»)."""
    builder = InlineKeyboardBuilder()
    today = date.today()
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        builder.button(text=_fmt_date(d), callback_data=f"rdate:{order_id}:{d.isoformat()}")
    builder.adjust(3)
    return builder.as_markup()


def ready_hours_kb(order_id: int, date_iso: str) -> InlineKeyboardMarkup:
    """Часы доставки 9–17 (последний слот 17:50). Данные зашиты в callback — без FSM."""
    builder = InlineKeyboardBuilder()
    for h in range(9, 18):
        builder.button(text=f"{h}:00–{h}:59", callback_data=f"rhour:{order_id}:{date_iso}:{h}")
    builder.adjust(3)
    return builder.as_markup()


def ready_minutes_kb(order_id: int, date_iso: str, hour: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for m in range(0, 60, 10):
        builder.button(
            text=f"{hour}:{m:02d}",
            callback_data=f"rmin:{order_id}:{date_iso}:{hour}:{m:02d}",
        )
    builder.adjust(3)
    return builder.as_markup()
