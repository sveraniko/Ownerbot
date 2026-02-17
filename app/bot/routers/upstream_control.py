from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.services.upstream_service import clear_runtime_override, get_upstream_snapshot, set_runtime_override
from app.core.logging import get_correlation_id
from app.core.settings import get_settings
from app.tools.providers.sis_gateway import upstream_unavailable
from app.upstream.sis_client import SisClient

router = Router()


@router.message(Command("sis_check"))
async def cmd_sis_check(message: Message) -> None:
    settings = get_settings()
    correlation_id = get_correlation_id()
    if not settings.sis_base_url:
        response = upstream_unavailable(correlation_id)
        await message.answer(f"Ошибка: {response.error.code}\nНе задан SIS_BASE_URL")
        return
    client = SisClient(settings)
    response = await client.ping(correlation_id=correlation_id)
    if response.status == "error":
        await message.answer(f"Ошибка: {response.error.code}\n{response.error.message}")
        return
    data = response.data
    await message.answer(
        "SIS ping: ok\n"
        f"service: {data.get('service', 'n/a')}\n"
        f"gateway: {data.get('gateway', 'n/a')}\n"
        f"as_of: {response.as_of.isoformat()}\n"
        f"filters_hash: {response.provenance.filters_hash or 'n/a'}"
    )


@router.message(Command("upstream"))
async def cmd_upstream(message: Message) -> None:
    state = await get_upstream_snapshot()
    await message.answer(
        "Upstream state\n"
        f"effective: {state.effective_mode}\n"
        f"runtime_override: {state.runtime_override or 'none'}\n"
        f"configured: {state.configured_mode}\n"
        f"last_ping(auto): {state.auto_ping}"
    )


async def _set_mode(message: Message, mode: str) -> None:
    await set_runtime_override(mode)
    await message.answer(f"Runtime upstream mode set to {mode}")


@router.message(Command("upstream_demo"))
async def cmd_upstream_demo(message: Message) -> None:
    await _set_mode(message, "DEMO")


@router.message(Command("upstream_sis"))
async def cmd_upstream_sis(message: Message) -> None:
    await _set_mode(message, "SIS_HTTP")


@router.message(Command("upstream_auto"))
async def cmd_upstream_auto(message: Message) -> None:
    await _set_mode(message, "AUTO")


@router.message(Command("upstream_clear"))
async def cmd_upstream_clear(message: Message) -> None:
    await clear_runtime_override()
    await message.answer("Runtime upstream override cleared")
