from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.bot.services.tool_runner import run_tool
from app.core.audit import write_audit_event
from app.core.db import check_db
from app.core.redis import check_redis
from app.diagnostics.diff import DiffItem, collect_differences
from app.tools.contracts import ToolActor, ToolResponse, ToolTenant
from app.tools.providers.sis_gateway import run_sis_tool
from app.tools.registry_setup import build_registry
from app.upstream.selector import resolve_effective_mode
from app.upstream.sis_client import SisClient


@dataclass(frozen=True)
class DiagnosticsContext:
    settings: Any
    redis: Any
    correlation_id: str
    sis_client: SisClient | None


@dataclass(frozen=True)
class SystemsReport:
    db_ok: bool
    redis_ok: bool
    effective_mode: str
    runtime_override: str | None
    configured_mode: str
    sis_status: str
    sis_latency_ms: int | None = None
    sis_error_code: str | None = None
    sis_contract_ok: bool | None = None
    sizebot_status: str = "disabled"


@dataclass(frozen=True)
class ShadowPresetResult:
    name: str
    status: str
    diff: list[DiffItem] = field(default_factory=list)
    error_code: str | None = None


@dataclass(frozen=True)
class ShadowReport:
    results: list[ShadowPresetResult]


registry = build_registry()
TENANT = ToolTenant(
    project="OwnerBot",
    shop_id="shop_001",
    currency="EUR",
    timezone="Europe/Berlin",
    locale="ru-RU",
)
ACTOR = ToolActor(owner_user_id=0)


async def _safe_audit(event_type: str, payload: dict[str, Any], *, correlation_id: str) -> None:
    try:
        await write_audit_event(event_type, payload, correlation_id=correlation_id)
    except Exception:
        return


async def run_systems_check(ctx: DiagnosticsContext) -> SystemsReport:
    await _safe_audit("systems_check_started", {"mode": ctx.settings.upstream_mode}, correlation_id=ctx.correlation_id)

    try:
        db_ok = await check_db()
    except Exception:
        db_ok = False

    try:
        redis_ok = await check_redis()
    except Exception:
        redis_ok = False

    try:
        effective_mode, runtime_override = await resolve_effective_mode(settings=ctx.settings, redis=ctx.redis)
    except Exception:
        effective_mode = ctx.settings.upstream_mode
        runtime_override = None

    sis_status = "disabled"
    sis_latency_ms: int | None = None
    sis_error_code: str | None = None
    sis_contract_ok: bool | None = None

    if ctx.sis_client and ctx.settings.sis_base_url:
        started = time.perf_counter()
        ping_response = await ctx.sis_client.ping(correlation_id=ctx.correlation_id)
        sis_latency_ms = int((time.perf_counter() - started) * 1000)
        if ping_response.status == "ok":
            sis_status = "ok"
            if ctx.settings.sis_contract_check_enabled:
                contract_resp = await _sis_contract_check(ctx)
                sis_contract_ok = contract_resp.status == "ok"
                if not sis_contract_ok:
                    sis_status = "degraded"
                    sis_error_code = contract_resp.error.code if contract_resp.error else "UNKNOWN"
        else:
            sis_status = "unavailable"
            sis_error_code = ping_response.error.code if ping_response.error else "UNKNOWN"

    if ctx.settings.sizebot_check_enabled:
        sizebot_status = "unavailable" if not ctx.settings.sizebot_base_url else "ok"
    else:
        sizebot_status = "disabled"

    report = SystemsReport(
        db_ok=db_ok,
        redis_ok=redis_ok,
        effective_mode=effective_mode,
        runtime_override=runtime_override,
        configured_mode=ctx.settings.upstream_mode,
        sis_status=sis_status,
        sis_latency_ms=sis_latency_ms,
        sis_error_code=sis_error_code,
        sis_contract_ok=sis_contract_ok,
        sizebot_status=sizebot_status,
    )
    await _safe_audit(
        "systems_check_finished",
        {
            "db_ok": report.db_ok,
            "redis_ok": report.redis_ok,
            "effective_mode": report.effective_mode,
            "sis_status": report.sis_status,
            "sizebot_status": report.sizebot_status,
        },
        correlation_id=ctx.correlation_id,
    )
    return report


async def _sis_contract_check(ctx: DiagnosticsContext) -> ToolResponse:
    today = date.today().isoformat()
    assert ctx.sis_client is not None
    return await ctx.sis_client.kpi_summary(
        from_date=today,
        to_date=today,
        tz="Europe/Berlin",
        correlation_id=ctx.correlation_id,
    )


async def run_shadow_check(ctx: DiagnosticsContext, presets: list[str]) -> ShadowReport:
    await _safe_audit("shadow_check_started", {"presets": presets}, correlation_id=ctx.correlation_id)
    results = await asyncio.gather(*[_run_shadow_preset(ctx, preset) for preset in presets])
    report = ShadowReport(results=list(results))
    await _safe_audit(
        "shadow_check_finished",
        {
            "presets": [result.name for result in report.results],
            "statuses": {result.name: result.status for result in report.results},
        },
        correlation_id=ctx.correlation_id,
    )
    return report


async def _run_shadow_preset(ctx: DiagnosticsContext, preset: str) -> ShadowPresetResult:
    tool_name, payload = _preset_call(preset)
    demo_response = await run_tool(
        tool_name,
        payload,
        actor=ACTOR,
        tenant=TENANT,
        correlation_id=ctx.correlation_id,
        registry=registry,
    )
    if demo_response.status != "ok":
        return ShadowPresetResult(name=preset, status="UNAVAILABLE", error_code=demo_response.error.code if demo_response.error else None)

    if not ctx.settings.sis_base_url:
        return ShadowPresetResult(name=preset, status="UNAVAILABLE", error_code="SIS_NOT_CONFIGURED")

    sis_response = await run_sis_tool(
        tool_name=tool_name,
        payload=payload,
        correlation_id=ctx.correlation_id,
        settings=ctx.settings,
    )
    if sis_response.status != "ok":
        return ShadowPresetResult(name=preset, status="UNAVAILABLE", error_code=sis_response.error.code if sis_response.error else None)

    differences = collect_differences(demo_response.data, sis_response.data, limit=5)
    if differences:
        diff_payload = {
            "preset": preset,
            "diff": [{"key": item.key, "demo": item.demo, "sis": item.sis} for item in differences],
        }
        await _safe_audit("shadow_mismatch", diff_payload, correlation_id=ctx.correlation_id)
        return ShadowPresetResult(name=preset, status="MISMATCH", diff=differences)

    return ShadowPresetResult(name=preset, status="OK")


def _preset_call(name: str) -> tuple[str, dict[str, Any]]:
    today = date.today()
    if name == "kpi_snapshot_7":
        return "kpi_snapshot", {"day": (today - timedelta(days=1)).isoformat()}
    if name == "revenue_trend_7":
        return "revenue_trend", {"days": 7}
    if name == "orders_search_stuck":
        return "orders_search", {"status": "stuck", "limit": 10}
    raise ValueError(f"Unknown shadow preset: {name}")


def format_systems_report(report: SystemsReport) -> str:
    db_icon = "✅" if report.db_ok else "❌"
    redis_icon = "✅" if report.redis_ok else "❌"
    lines = [
        f"OwnerBot: DB {db_icon} / Redis {redis_icon}",
        f"Upstream: effective_mode={report.effective_mode} (override={report.runtime_override or 'None'})",
    ]

    if report.sis_status == "disabled":
        lines.append("SIS: disabled")
    elif report.sis_status == "ok":
        contract = "n/a"
        if report.sis_contract_ok is True:
            contract = "OK"
        elif report.sis_contract_ok is False:
            contract = "FAIL"
        latency = f" latency={report.sis_latency_ms}ms" if report.sis_latency_ms is not None else ""
        lines.append(f"SIS: ping ✅{latency}, contract={contract}")
    elif report.sis_status == "degraded":
        latency = f" latency={report.sis_latency_ms}ms" if report.sis_latency_ms is not None else ""
        lines.append(f"SIS: ping ⚠️{latency}, contract=FAIL ({report.sis_error_code or 'UNKNOWN'})")
    else:
        lines.append(f"SIS: UNAVAILABLE ({report.sis_error_code or 'UNKNOWN'})")

    lines.append(f"SizeBot: {report.sizebot_status}")
    return "\n".join(lines)


def format_shadow_report(report: ShadowReport) -> str:
    title = "Shadow check (DEMO vs SIS)"
    lines = [title]
    for result in report.results:
        lines.append(f"- {result.name}: {result.status}")
        if result.status == "MISMATCH":
            for item in result.diff:
                lines.append(f"  • {item.key}: demo={item.demo} | sis={item.sis}")
        if result.status == "UNAVAILABLE" and result.error_code:
            lines.append(f"  • reason={result.error_code}")
    return "\n".join(lines)
