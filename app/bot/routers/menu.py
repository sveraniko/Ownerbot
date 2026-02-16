from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.services.menu_entrypoints import show_help, show_main_menu, show_systems, show_templates_home, show_tools, show_upstream

router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await show_main_menu(message, state)


@router.message(F.text == "📚 Шаблоны")
async def menu_templates(message: Message, state: FSMContext) -> None:
    await show_templates_home(message, state)


@router.message(F.text == "⚙️ Системы")
async def menu_systems(message: Message, state: FSMContext) -> None:
    await show_systems(message, state)


@router.message(F.text == "🔌 Upstream")
async def menu_upstream(message: Message, state: FSMContext) -> None:
    await show_upstream(message, state)


@router.message(F.text == "🧰 Tools")
async def menu_tools(message: Message, state: FSMContext) -> None:
    await show_tools(message, state)


@router.message(F.text == "🆘 Help")
async def menu_help(message: Message, state: FSMContext) -> None:
    await show_help(message, state)
