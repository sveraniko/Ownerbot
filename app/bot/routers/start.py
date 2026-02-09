from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.db import check_db
from app.core.redis import check_redis
from app.core.settings import get_settings

router = Router()


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

    text = (
        "OwnerBot online.\n\n"
        f"DB: {'ok' if db_ok else 'fail'}\n"
        f"Redis: {'ok' if redis_ok else 'fail'}\n"
        f"Owner IDs: {', '.join(str(x) for x in settings.owner_ids) or 'none'}\n"
        f"Mode: {settings.upstream_mode}\n\n"
        "Примеры:\n"
        "• дай KPI за вчера\n"
        "• что с заказами, что зависло\n"
        "• покажи последние 7 дней выручку\n"
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "Примеры фраз:\n"
        "• дай KPI за вчера\n"
        "• что с заказами, что зависло\n"
        "• покажи последние 7 дней выручку\n"
    )
    await message.answer(text)
