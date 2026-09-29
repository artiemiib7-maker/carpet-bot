import asyncio
import logging
from datetime import date

from aiogram import Bot

import sheets
from config import TEXTS
from keyboards import delivery_notice_kb, ready_dates_kb

log = logging.getLogger(__name__)

CHECK_INTERVAL = 3600  # секунд — раз в час


async def check_and_notify(bot: Bot) -> None:
    """Одна итерация: ищет заказы с доставкой сегодня и шлёт уведомления."""
    today = date.today().isoformat()
    due = await asyncio.to_thread(sheets.get_orders_due_today, today)
    for order in due:
        order_id = order.get("id")
        telegram_id = order.get("telegram_id")
        try:
            telegram_id = int(telegram_id)
        except (TypeError, ValueError):
            log.warning("Заказ #%s: некорректный telegram_id %r", order_id, telegram_id)
            continue
        try:
            await bot.send_message(
                telegram_id,
                f"Заказ №{order_id}: {TEXTS['notified_intro']}",
                reply_markup=delivery_notice_kb(order_id),
            )
            await asyncio.to_thread(sheets.mark_notified, order_id)
            log.info("Уведомление о доставке отправлено: заказ #%s", order_id)
        except Exception:
            log.exception("Не удалось отправить уведомление по заказу #%s", order_id)


async def check_ready_and_notify(bot: Bot) -> None:
    """Заказы со статусом «упакован»: «ковёр готов, выберите дату и время доставки»."""
    ready = await asyncio.to_thread(sheets.get_ready_orders)
    for order in ready:
        order_id = order.get("id")
        telegram_id = order.get("telegram_id")
        try:
            telegram_id = int(telegram_id)
        except (TypeError, ValueError):
            log.warning("Заказ #%s: некорректный telegram_id %r", order_id, telegram_id)
            continue
        try:
            await bot.send_message(
                telegram_id,
                f"Заказ №{order_id}: {TEXTS['ready_for_delivery']}",
                reply_markup=ready_dates_kb(int(order_id)),
            )
            await asyncio.to_thread(sheets.mark_ready_notified, order_id)
            log.info("Уведомление «ковёр готов» отправлено: заказ #%s", order_id)
        except Exception:
            log.exception("Не удалось отправить «ковёр готов» по заказу #%s", order_id)


async def notifier_loop(bot: Bot) -> None:
    """Фоновая задача: раз в час проверяет готовые ковры и даты доставки."""
    if not sheets.init():
        log.warning("Notifier отключён: Google Sheets недоступен.")
        return
    while True:
        try:
            await check_ready_and_notify(bot)
            await check_and_notify(bot)
        except Exception:
            log.exception("Ошибка в цикле уведомлений")
        await asyncio.sleep(CHECK_INTERVAL)
