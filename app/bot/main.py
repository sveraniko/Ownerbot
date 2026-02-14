from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot.middlewares.correlation import CorrelationMiddleware
from app.bot.middlewares.owner_gate import OwnerGateMiddleware
from app.bot.routers import actions, diagnostics, owner_console, start, templates, upstream_control
from app.core.logging import configure_logging
from app.core.preflight import format_preflight_report, preflight_validate_settings
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.storage.bootstrap import run_migrations, seed_demo_data
from app.upstream.selector import resolve_effective_mode

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.middleware(CorrelationMiddleware())
    dispatcher.message.middleware(OwnerGateMiddleware())
    dispatcher.callback_query.middleware(CorrelationMiddleware())
    dispatcher.callback_query.middleware(OwnerGateMiddleware())
    dispatcher.include_router(start.router)
    dispatcher.include_router(templates.router)
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


async def _resolve_mode_for_preflight(settings) -> tuple[str, str | None, bool]:
    try:
        redis = await get_redis()
    except Exception:
        return settings.upstream_mode, None, False

    try:
        if not await redis.ping():
            return settings.upstream_mode, None, False
    except Exception:
        return settings.upstream_mode, None, False

    try:
        effective_mode, runtime_override = await resolve_effective_mode(settings=settings, redis=redis)
        return effective_mode, runtime_override, True
    except Exception:
        return settings.upstream_mode, None, False


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    effective_mode, runtime_override, redis_available_for_mode = asyncio.run(_resolve_mode_for_preflight(settings))
    preflight_report = preflight_validate_settings(
        settings,
        effective_mode=effective_mode,
        runtime_override=runtime_override,
        redis_available_for_mode=redis_available_for_mode,
    )
    preflight_text = format_preflight_report(preflight_report)

    if not preflight_report.ok and settings.preflight_fail_fast:
        logger.error(
            "preflight_failed",
            extra={
                "summary": preflight_text,
                "codes": [item.code for item in preflight_report.items],
                "errors": preflight_report.errors_count,
                "warnings": preflight_report.warnings_count,
            },
        )
        raise SystemExit(2)

    log_method = logger.warning if preflight_report.warnings_count or not preflight_report.ok else logger.info
    log_method(
        "preflight_checked",
        extra={
            "summary": preflight_text,
            "codes": [item.code for item in preflight_report.items],
            "errors": preflight_report.errors_count,
            "warnings": preflight_report.warnings_count,
        },
    )

    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher()
    asyncio.run(start_polling(dispatcher, bot))


async def start_polling(dispatcher: Dispatcher, bot: Bot) -> None:
    await on_startup()
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    main()
