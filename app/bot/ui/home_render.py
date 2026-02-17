from __future__ import annotations

from aiogram.types import Message

from app.bot.ui.anchor_panel import render_anchor_panel
from app.bot.ui.home_keyboard import build_home_keyboard
from app.bot.ui.home_panel import build_home_text


async def render_home_panel(message: Message) -> int:
    return await render_anchor_panel(message, text=await build_home_text(), reply_markup=build_home_keyboard())
