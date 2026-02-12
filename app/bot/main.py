from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.middlewares.correlation import CorrelationMiddleware
from app.bot.middlewares.owner_gate import OwnerGateMiddleware
from app.bot.routers import actions, diagnostics, owner_console, start, upstream_control
from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.storage.bootstrap import run_migrations, seed_demo_data

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.middleware(CorrelationMiddleware())
    dispatcher.message.middleware(OwnerGateMiddleware())
    dispatcher.callback_query.middleware(CorrelationMiddleware())
    dispatcher.callback_query.middleware(OwnerGateMiddleware())
    dispatcher.include_router(start.router)
    dispatcher.include_router(owner_console.router)
    dispatcher.include_router(upstream_control.router)
    dispatcher.include_router(diagnostics.router)
    dispatcher.include_router(actions.router)
    return dispatcher


async def on_startup() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_migrations)
    await seed_demo_data()
    logger.info("startup_complete")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher()
    asyncio.run(start_polling(dispatcher, bot))


async def start_polling(dispatcher: Dispatcher, bot: Bot) -> None:
    await on_startup()
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    main()
