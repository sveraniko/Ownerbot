from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.services.menu_entrypoints import show_help, show_tools
from app.bot.ui.formatting import format_start_message
from app.bot.ui.main_menu import build_main_menu_kb
from app.bot.ui.panel_manager import get_panel_manager
from app.core.db import check_db
from app.core.redis import check_redis, get_redis
from app.core.settings import get_settings
from app.upstream.selector import resolve_effective_mode

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    panel = get_panel_manager()
    settings = get_settings()
    db_ok = False
    redis_ok = False
    effective_mode = settings.upstream_mode

    try:
        db_ok = await check_db()
    except Exception:
        db_ok = False
    try:
        redis_ok = await check_redis()
    except Exception:
        redis_ok = False

    try:
        redis = await get_redis()
        if await redis.ping():
            effective_mode, _ = await resolve_effective_mode(settings=settings, redis=redis)
    except Exception:
        effective_mode = settings.upstream_mode

    text = format_start_message(
        {
            "db_ok": db_ok,
            "redis_ok": redis_ok,
            "owner_ids_text": ", ".join(str(x) for x in settings.owner_ids) or "none",
            "configured_mode": settings.upstream_mode,
            "effective_mode": effective_mode,
            "asr_provider": settings.asr_provider,
            "llm_provider": settings.llm_provider,
        }
    )
    text += "\nУправление: /templates или кнопка 📚 Шаблоны"

    await panel.clear_panel(message.chat.id, bot=message.bot)
    await panel.clear_transients(message.chat.id, bot=message.bot)
    await panel.ensure_home(message, text, reply_kb=build_main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await show_help(message)


@router.message(Command("tools"))
async def cmd_tools(message: Message) -> None:
    await show_tools(message)


@router.message(Command("clean"))
async def cmd_clean(message: Message) -> None:
    panel = get_panel_manager()
    await panel.clear_panel(message.chat.id, bot=message.bot)
    await panel.clear_transients(message.chat.id, bot=message.bot)
    await panel.ensure_home(message, "OwnerBot online", reply_kb=build_main_menu_kb())
