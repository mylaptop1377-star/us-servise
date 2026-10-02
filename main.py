import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from bot.config import Settings
from bot.database.engine import create_database
from bot.handlers import admin, start, uc_order
from bot.services.midasbuy import MidasbuyClient


async def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required. Copy .env.example to .env and configure it.")
    if not settings.admin_ids:
        logging.getLogger(__name__).warning(
            "ADMIN_IDS is empty; orders can be saved but no admin can review them."
        )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    engine = None
    try:
        sessions, engine = await create_database(settings.database_url)
        timeout = aiohttp.ClientTimeout(total=15)
        dp = Dispatcher(storage=MemoryStorage())
        dp["sessions"] = sessions
        dp["settings"] = settings
        dp.include_routers(admin.router, uc_order.router, start.router)
        async with aiohttp.ClientSession(timeout=timeout) as http_session:
            dp["midasbuy"] = MidasbuyClient(http_session, settings)
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        if engine is not None:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
