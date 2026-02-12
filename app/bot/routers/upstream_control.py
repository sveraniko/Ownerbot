from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.tools.providers.sis_gateway import upstream_unavailable
from app.upstream.mode_store import set_runtime_mode
from app.upstream.selector import resolve_effective_mode
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
    settings = get_settings()
    redis = await get_redis()
    effective_mode, runtime_mode = await resolve_effective_mode(settings=settings, redis=redis)
    cached_ping = "n/a"
    if effective_mode == "AUTO" or runtime_mode == "AUTO":
        try:
            cached_ping = "ok" if await redis.get(":auto_ping_ok") == "1" else "unknown"
        except Exception:
            cached_ping = "unknown"
    await message.answer(
        "Upstream state\n"
        f"effective: {effective_mode}\n"
        f"runtime_override: {runtime_mode or 'none'}\n"
        f"configured: {settings.upstream_mode}\n"
        f"last_ping(auto): {cached_ping}"
    )


async def _set_mode(message: Message, mode: str) -> None:
    settings = get_settings()
    redis = await get_redis()
    await set_runtime_mode(redis, settings.upstream_redis_key, mode)
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
