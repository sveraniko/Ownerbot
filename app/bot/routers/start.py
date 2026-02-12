from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.ui.formatting import format_start_message, format_tools_list
from app.core.db import check_db
from app.core.redis import check_redis
from app.core.settings import get_settings
from app.tools.registry_setup import build_registry

router = Router()
registry = build_registry()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    settings = get_settings()
    db_ok = False
    redis_ok = False
    try:
        db_ok = await check_db()
    except Exception:
        db_ok = False
    try:
        redis_ok = await check_redis()
    except Exception:
        redis_ok = False

    text = format_start_message(
        {
            "db_ok": db_ok,
            "redis_ok": redis_ok,
            "owner_ids_text": ", ".join(str(x) for x in settings.owner_ids) or "none",
            "mode": settings.upstream_mode,
        }
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "Примеры фраз:\n"
        "• дай KPI за вчера\n"
        "• что с заказами, что зависло\n"
        "• /trend 14\n"
        "• график выручки 7 дней\n"
        "• /weekly_pdf\n"
        "• флагни заказ OB-1003 причина тест\n"
    )
    await message.answer(text)


@router.message(Command("tools"))
async def cmd_tools(message: Message) -> None:
    await message.answer(format_tools_list(registry.list_definitions()))
