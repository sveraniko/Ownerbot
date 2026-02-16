from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.services.menu_entrypoints import show_upstream
from app.bot.ui.panel_manager import get_panel_manager
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.tools.providers.sis_gateway import upstream_unavailable
from app.upstream.mode_store import set_runtime_mode
from app.upstream.sis_client import SisClient

router = Router()


@router.message(Command("sis_check"))
async def cmd_sis_check(message: Message) -> None:
    panel = get_panel_manager()
    settings = get_settings()
    correlation_id = get_correlation_id()
    if not settings.sis_base_url:
        response = upstream_unavailable(correlation_id)
        await panel.show_panel(
            message,
            f"Ошибка: {response.error.code}\nНе задан SIS_BASE_URL",
            mode="replace",
        )
        return
    client = SisClient(settings)
    response = await client.ping(correlation_id=correlation_id)
    if response.status == "error":
        await panel.show_panel(
            message,
            f"Ошибка: {response.error.code}\n{response.error.message}",
            mode="replace",
        )
        return
    data = response.data
    await panel.show_panel(
        message,
        "SIS ping: ok\n"
        f"service: {data.get('service', 'n/a')}\n"
        f"gateway: {data.get('gateway', 'n/a')}\n"
        f"as_of: {response.as_of.isoformat()}\n"
        f"filters_hash: {response.provenance.filters_hash or 'n/a'}",
        mode="replace",
    )


@router.message(Command("upstream"))
async def cmd_upstream(message: Message) -> None:
    await show_upstream(message)


async def _set_mode(message: Message, mode: str) -> None:
    panel = get_panel_manager()
    settings = get_settings()
    redis = await get_redis()
    await set_runtime_mode(redis, settings.upstream_redis_key, mode)
    await panel.show_panel(message, f"Runtime upstream mode set to {mode}", mode="replace")


@router.message(Command("upstream_demo"))
async def cmd_upstream_demo(message: Message) -> None:
    await _set_mode(message, "DEMO")


@router.message(Command("upstream_sis"))
async def cmd_upstream_sis(message: Message) -> None:
    await _set_mode(message, "SIS_HTTP")


@router.message(Command("upstream_auto"))
async def cmd_upstream_auto(message: Message) -> None:
    await _set_mode(message, "AUTO")
