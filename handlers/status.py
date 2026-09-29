import asyncio

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import sheets
from config import ORDER_STAGES

router = Router()

_STAGE_ICONS = {
    "отгружен": "1️⃣",
    "принят": "2️⃣",
    "упакован": "3️⃣",
    "доставлен": "4️⃣",
}


def _stage_line(status: str) -> str:
    status = status.strip().lower()
    if status not in ORDER_STAGES:
        return f"Этап: {status or 'не задан'}"
    idx = ORDER_STAGES.index(status)
    parts = []
    for i, stage in enumerate(ORDER_STAGES):
        label = f"<b>{stage}</b>" if i == idx else stage
        parts.append(f"{_STAGE_ICONS[stage]} {label}")
    return "Этап: " + " → ".join(parts)


def _total_with_fee(order: dict) -> str:
    fee = order.get("доплата_перенос") or 0
    try:
        return f"{float(str(order.get('итого_₽', 0)).replace(',', '.')) + float(fee):g}"
    except (ValueError, TypeError):
        return str(order.get("итого_₽", "?"))


@router.message(F.text == "📋 Мои заказы")
async def my_orders(message: Message):
    orders = await asyncio.to_thread(sheets.get_orders_by_user, message.from_user.id)
    if not sheets.init():
        await message.answer(
            "База заказов (Google Sheets) пока не настроена. "
            "Попробуйте позже или уточните статус по телефону."
        )
        return
    if not orders:
        await message.answer("У вас пока нет заказов. Нажмите «🧺 Оформить заказ».")
        return
    for order in reversed(orders[-10:]):
        status = str(order.get("статус", "")).strip().lower()
        delivery = str(order.get("дата_доставки", "")).strip()
        text = (
            f"<b>Заказ №{order.get('id')}</b>\n"
            f"Город: {order.get('город')}\n"
            f"{_stage_line(status)}\n"
            f"Дата доставки: {delivery or 'будет согласована'}\n"
            f"Сумма: {_total_with_fee(order)} ₽"
        )
        # Ковёр упакован, но дата доставки ещё не выбрана — предлагаем выбрать.
        if status == "упакован" and not delivery:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="📅 Выбрать дату и время доставки",
                    callback_data=f"pickdate:{order.get('id')}",
                )
            ]])
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.answer(text, parse_mode="HTML")
