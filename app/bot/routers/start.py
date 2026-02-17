from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.ui.home_render import render_home_panel
from app.bot.ui.formatting import format_tools_list
from app.tools.registry_setup import build_registry

router = Router()
registry = build_registry()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await render_home_panel(message)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    text = (
        "Примеры фраз:\n"
        "• дай KPI за вчера\n"
        "• что с заказами, что зависло\n"
        "• /trend 14\n"
        "• график выручки 7 дней\n"
        "• /weekly_pdf\n"
        "• прогноз спроса\n"
        "• план дозакупки\n"
        "• флагни заказ OB-1003 причина тест\n"
    )
    await message.answer(text)


@router.message(Command("tools"))
async def cmd_tools(message: Message) -> None:
    await message.answer(format_tools_list(registry.list_definitions()))
