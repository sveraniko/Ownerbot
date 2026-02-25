from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.services.upstream_service import clear_runtime_override, get_upstream_snapshot, set_runtime_override
from app.bot.ui.home_keyboard import build_home_keyboard
from app.bot.ui.home_panel import build_home_text
from app.bot.ui.home_render import render_home_panel
from app.bot.ui.sections import (
    build_dashboard_panel,
    build_advisor_panel,
    build_focus_burn_panel,
    build_focus_money_panel,
    build_focus_stock_panel,
    build_notifications_panel,
    build_orders_panel,
    build_prices_panel,
    build_products_panel,
    build_systems_panel,
    build_tools_panel,
)
from app.bot.ui.templates_keyboards import build_templates_main_keyboard

router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await render_home_panel(message)


@router.callback_query(F.data == "ui:home")
async def ui_home(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text(await build_home_text(), reply_markup=build_home_keyboard())
    await callback_query.answer()


@router.callback_query(F.data == "ui:templates")
async def ui_templates(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text("Шаблоны", reply_markup=build_templates_main_keyboard())
    await callback_query.answer()


@router.callback_query(F.data == "ui:dash")
async def ui_dash(callback_query: CallbackQuery) -> None:
    text, keyboard = build_dashboard_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "ui:advisor")
async def ui_advisor(callback_query: CallbackQuery) -> None:
    text, keyboard = build_advisor_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "ui:focus:burn")
async def ui_focus_burn(callback_query: CallbackQuery) -> None:
    text, keyboard = build_focus_burn_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "ui:focus:money")
async def ui_focus_money(callback_query: CallbackQuery) -> None:
    text, keyboard = build_focus_money_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "ui:focus:stock")
async def ui_focus_stock(callback_query: CallbackQuery) -> None:
    text, keyboard = build_focus_stock_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()

@router.callback_query(F.data == "ui:orders")
async def ui_orders(callback_query: CallbackQuery) -> None:
    text, keyboard = build_orders_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "ui:prices")
async def ui_prices(callback_query: CallbackQuery) -> None:
    text, keyboard = build_prices_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "ui:products")
async def ui_products(callback_query: CallbackQuery) -> None:
    text, keyboard = build_products_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "ui:notify")
async def ui_notify(callback_query: CallbackQuery) -> None:
    text, keyboard = build_notifications_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "ui:systems")
async def ui_systems(callback_query: CallbackQuery) -> None:
    text, keyboard = build_systems_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


def _upstream_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="DEMO", callback_data="ui:upstream:set:DEMO"),
                InlineKeyboardButton(text="AUTO", callback_data="ui:upstream:set:AUTO"),
                InlineKeyboardButton(text="SIS_HTTP", callback_data="ui:upstream:set:SIS_HTTP"),
            ],
            [InlineKeyboardButton(text="Сбросить", callback_data="ui:upstream:clear")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="ui:systems")],
            [InlineKeyboardButton(text="🏠 Главная", callback_data="ui:home")],
        ]
    )


async def _upstream_text() -> str:
    state = await get_upstream_snapshot()
    return (
        "🔌 Upstream\n\n"
        f"configured: {state.configured_mode}\n"
        f"effective: {state.effective_mode}\n"
        f"runtime_override: {state.runtime_override or 'none'}\n"
        f"last_ping(auto): {state.auto_ping}"
    )


@router.callback_query(F.data == "ui:upstream")
async def ui_upstream(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text(await _upstream_text(), reply_markup=_upstream_keyboard())
    await callback_query.answer()


@router.callback_query(F.data.startswith("ui:upstream:set:"))
async def ui_upstream_set(callback_query: CallbackQuery) -> None:
    mode = callback_query.data.split(":")[-1]
    await set_runtime_override(mode)
    await callback_query.message.edit_text(await _upstream_text(), reply_markup=_upstream_keyboard())
    await callback_query.answer("Updated")


@router.callback_query(F.data == "ui:upstream:clear")
async def ui_upstream_clear(callback_query: CallbackQuery) -> None:
    await clear_runtime_override()
    await callback_query.message.edit_text(await _upstream_text(), reply_markup=_upstream_keyboard())
    await callback_query.answer("Cleared")


@router.callback_query(F.data == "ui:tools")
async def ui_tools(callback_query: CallbackQuery) -> None:
    text, keyboard = build_tools_panel()
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()
