from __future__ import annotations

from aiogram.types import Message

from app.bot.ui.formatting import format_tools_list
from app.bot.ui.templates_keyboards import build_templates_main_keyboard
from app.bot.ui.main_menu import build_main_menu_kb
from app.bot.ui.panel_manager import get_panel_manager
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.diagnostics.systems import DiagnosticsContext, run_systems_check
from app.diagnostics.systems import format_systems_report as format_diag_systems_report
from app.tools.registry_setup import build_registry
from app.upstream.selector import resolve_effective_mode
from app.upstream.sis_client import SisClient

registry = build_registry()
_STATE_KEY = "ownerbot:templates:state:"


async def show_main_menu(message: Message) -> None:
    panel = get_panel_manager()
    await panel.ensure_home(
        message,
        "Главное меню OwnerBot. Выберите раздел кнопкой или используйте slash-команды.",
        reply_kb=build_main_menu_kb(),
    )


async def show_templates_home(message: Message) -> None:
    panel = get_panel_manager()
    redis = await get_redis()
    await redis.delete(f"{_STATE_KEY}{message.from_user.id}")
    await panel.show_panel(
        message,
        "Шаблоны",
        inline_kb=build_templates_main_keyboard(),
        mode="replace",
    )


async def show_systems(message: Message) -> None:
    panel = get_panel_manager()
    settings = get_settings()
    if not settings.diagnostics_enabled:
        await panel.show_panel(message, "Diagnostics disabled by config.", mode="replace")
        return

    try:
        redis = await get_redis()
    except Exception:
        redis = None
    correlation_id = get_correlation_id()
    sis_client = SisClient(settings) if settings.sis_base_url else None

    report = await run_systems_check(
        DiagnosticsContext(
            settings=settings,
            redis=redis,
            correlation_id=correlation_id,
            sis_client=sis_client,
        )
    )
    await panel.show_panel(message, format_diag_systems_report(report), mode="replace")


async def show_upstream(message: Message) -> None:
    panel = get_panel_manager()
    settings = get_settings()
    redis = await get_redis()
    effective_mode, runtime_mode = await resolve_effective_mode(settings=settings, redis=redis)
    cached_ping = "n/a"
    if effective_mode == "AUTO" or runtime_mode == "AUTO":
        try:
            cached_ping = "ok" if await redis.get(":auto_ping_ok") == "1" else "unknown"
        except Exception:
            cached_ping = "unknown"
    await panel.show_panel(
        message,
        "Upstream state\n"
        f"effective: {effective_mode}\n"
        f"runtime_override: {runtime_mode or 'none'}\n"
        f"configured: {settings.upstream_mode}\n"
        f"last_ping(auto): {cached_ping}",
        mode="replace",
    )


async def show_help(message: Message) -> None:
    panel = get_panel_manager()
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
    await panel.show_panel(message, text, mode="replace")


async def show_tools(message: Message) -> None:
    panel = get_panel_manager()
    await panel.show_panel(message, format_tools_list(registry.list_definitions()), mode="replace")
