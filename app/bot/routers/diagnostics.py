from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.diagnostics.systems import DiagnosticsContext, format_shadow_report, format_systems_report, run_shadow_check, run_systems_check
from app.upstream.sis_client import SisClient

router = Router()
DEFAULT_SHADOW_PRESETS = ["kpi_snapshot_7", "revenue_trend_7", "orders_search_stuck"]


@router.message(Command("systems"))
async def cmd_systems(message: Message) -> None:
    settings = get_settings()
    if not settings.diagnostics_enabled:
        await message.answer("Diagnostics disabled by config.")
        return

    redis = await get_redis()
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
    await message.answer(format_systems_report(report))


@router.message(Command("shadow_check"))
async def cmd_shadow_check(message: Message) -> None:
    settings = get_settings()
    if not settings.diagnostics_enabled or not settings.shadow_check_enabled:
        await message.answer("Shadow check disabled by config.")
        return

    redis = await get_redis()
    correlation_id = get_correlation_id()
    sis_client = SisClient(settings) if settings.sis_base_url else None

    report = await run_shadow_check(
        DiagnosticsContext(
            settings=settings,
            redis=redis,
            correlation_id=correlation_id,
            sis_client=sis_client,
        ),
        presets=DEFAULT_SHADOW_PRESETS,
    )
    await message.answer(format_shadow_report(report))
