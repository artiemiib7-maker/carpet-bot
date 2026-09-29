import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
import sheets
from handlers import start, order, status, delivery
from notifier import notifier_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Создайте .env (см. README.md).")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_routers(start.router, order.router, status.router, delivery.router)

    sheets.init()  # предупредит в лог, если credentials.json ещё нет
    notifier_task = asyncio.create_task(notifier_loop(bot))

    log.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        notifier_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
