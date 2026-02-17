from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.services.upstream_service import clear_runtime_override, get_upstream_snapshot, set_runtime_override
from app.bot.ui.home_keyboard import build_home_keyboard
from app.bot.ui.home_panel import build_home_text
from app.bot.ui.home_render import render_home_panel
from app.bot.ui.templates_keyboards import build_templates_main_keyboard
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.diagnostics.systems import DiagnosticsContext, run_systems_check
from app.upstream.sis_client import SisClient

router = Router()



async def _systems_mini_panel_text() -> str:
    settings = get_settings()
    if not settings.diagnostics_enabled:
        return "⚙️ Системы\n\nDiagnostics disabled by config."

    try:
        redis = await get_redis()
    except Exception:
        redis = None

    report = await run_systems_check(
        DiagnosticsContext(
            settings=settings,
            redis=redis,
            correlation_id=get_correlation_id(),
            sis_client=SisClient(settings) if settings.sis_base_url else None,
        )
    )
    return (
        "⚙️ Системы\n\n"
        f"DB: {'✅' if report.db_ok else '❌'}\n"
        f"Redis: {'✅' if report.redis_ok else '❌'}\n"
        f"Upstream: cfg={report.configured_mode}, eff={report.effective_mode}\n"
        f"SIS runtime: {report.sis_status}"
    )


def _home_button_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Home", callback_data="ui:home")]])


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


@router.callback_query(F.data == "ui:systems")
async def ui_systems(callback_query: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="ui:systems")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="ui:home")],
        ]
    )
    await callback_query.message.edit_text(await _systems_mini_panel_text(), reply_markup=keyboard)
    await callback_query.answer()


def _upstream_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="DEMO", callback_data="ui:upstream:set:DEMO"),
                InlineKeyboardButton(text="AUTO", callback_data="ui:upstream:set:AUTO"),
                InlineKeyboardButton(text="SIS_HTTP", callback_data="ui:upstream:set:SIS_HTTP"),
            ],
            [InlineKeyboardButton(text="Clear override", callback_data="ui:upstream:clear")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="ui:home")],
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
    settings = get_settings()
    tools = settings.llm_allowed_action_tools
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 List tools as message", callback_data="ui:tools:list")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="ui:home")],
        ]
    )
    await callback_query.message.edit_text(
        "🧰 Tools\n\n"
        f"allowed_action_tools: {len(tools)}\n"
        f"{', '.join(tools) if tools else 'none'}",
        reply_markup=keyboard,
    )
    await callback_query.answer()


@router.callback_query(F.data == "ui:tools:list")
async def ui_tools_list(callback_query: CallbackQuery) -> None:
    settings = get_settings()
    tools = settings.llm_allowed_action_tools
    if tools:
        await callback_query.message.answer("Allowed tools:\n" + "\n".join(f"• {name}" for name in tools))
    else:
        await callback_query.message.answer("Allowed tools:\n• none")
    await callback_query.answer()


@router.callback_query(F.data == "ui:help")
async def ui_help(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text(
        "🆘 Help\n\n/start, /menu, /templates\n/systems, /upstream, /tools",
        reply_markup=_home_button_keyboard(),
    )
    await callback_query.answer()
