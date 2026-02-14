from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.bot.services.tool_runner import run_tool
from app.core.audit import write_audit_event
from app.core.db import check_db
from app.core.preflight import preflight_validate_settings
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
    preflight_status: str = "OK"
    preflight_codes: list[str] = field(default_factory=list)
    asr_provider: str = "mock"
    asr_convert_voice_ogg_to_wav: bool = True
    asr_max_seconds: int = 0
    asr_max_bytes: int = 0
    asr_timeout_sec: int = 0
    openai_key_present: bool = False
    llm_provider: str = "OFF"
    llm_timeout_seconds: int = 0
    llm_allowed_action_tools: list[str] = field(default_factory=list)
    sis_base_url_present: bool = False
    sis_api_key_present: bool = False
    sis_contract_check_enabled: bool = False
    sizebot_check_enabled: bool = False
    sizebot_base_url_present: bool = False
    sizebot_api_key_present: bool = False


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
TENANT = ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU")
ACTOR = ToolActor(owner_user_id=0)


async def _safe_audit(event_type: str, payload: dict[str, Any], *, correlation_id: str) -> None:
    try:
        await write_audit_event(event_type, payload, correlation_id=correlation_id)
    except Exception:
        return


async def _resolve_mode_for_diagnostics(settings: Any, redis: Any) -> tuple[str, str | None, bool]:
    redis_available = False
    if redis is not None:
        try:
            redis_available = bool(await redis.ping())
        except Exception:
            redis_available = False

    if redis_available:
        try:
            effective_mode, runtime_override = await resolve_effective_mode(settings=settings, redis=redis)
            return effective_mode, runtime_override, True
        except Exception:
            return settings.upstream_mode, None, False

    return settings.upstream_mode, None, False


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

    effective_mode, runtime_override, redis_available_for_mode = await _resolve_mode_for_diagnostics(ctx.settings, ctx.redis)

    preflight_report = preflight_validate_settings(
        ctx.settings,
        effective_mode=effective_mode,
        runtime_override=runtime_override,
        redis_available_for_mode=redis_available_for_mode,
    )
    preflight_status = "FAIL" if preflight_report.errors_count else ("WARN" if preflight_report.warnings_count else "OK")

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

    sizebot_status = "disabled"
    if ctx.settings.sizebot_check_enabled:
        sizebot_status = "unavailable" if not ctx.settings.sizebot_base_url else "ok"

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
        preflight_status=preflight_status,
        preflight_codes=[item.code for item in preflight_report.items[:5]],
        asr_provider=ctx.settings.asr_provider,
        asr_convert_voice_ogg_to_wav=ctx.settings.asr_convert_voice_ogg_to_wav,
        asr_max_seconds=ctx.settings.asr_max_seconds,
        asr_max_bytes=ctx.settings.asr_max_bytes,
        asr_timeout_sec=ctx.settings.asr_timeout_sec,
        openai_key_present=bool(str(ctx.settings.openai_api_key or "").strip()),
        llm_provider=ctx.settings.llm_provider,
        llm_timeout_seconds=ctx.settings.llm_timeout_seconds,
        llm_allowed_action_tools=list(ctx.settings.llm_allowed_action_tools),
        sis_base_url_present=bool(str(ctx.settings.sis_base_url or "").strip()),
        sis_api_key_present=bool(str(ctx.settings.sis_ownerbot_api_key or "").strip()),
        sis_contract_check_enabled=ctx.settings.sis_contract_check_enabled,
        sizebot_check_enabled=ctx.settings.sizebot_check_enabled,
        sizebot_base_url_present=bool(str(ctx.settings.sizebot_base_url or "").strip()),
        sizebot_api_key_present=bool(str(ctx.settings.sizebot_api_key or "").strip()),
    )
    await _safe_audit(
        "systems_check_finished",
        {
            "db_ok": report.db_ok,
            "redis_ok": report.redis_ok,
            "effective_mode": report.effective_mode,
            "sis_status": report.sis_status,
            "sizebot_status": report.sizebot_status,
            "preflight_status": report.preflight_status,
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
    runtime_override = report.runtime_override or "None"
    preflight_codes = ", ".join(report.preflight_codes) if report.preflight_codes else "none"

    lines = [
        f"OwnerBot: DB {db_icon} / Redis {redis_icon}",
        f"Upstream: configured={report.configured_mode}, effective={report.effective_mode}, runtime_override={runtime_override}",
        (
            "ASR: "
            f"provider={report.asr_provider}, convert_ogg_to_wav={report.asr_convert_voice_ogg_to_wav}, "
            f"max_seconds={report.asr_max_seconds}, max_bytes={report.asr_max_bytes}, "
            f"timeout={report.asr_timeout_sec}s, openai_key_present={'yes' if report.openai_key_present else 'no'}"
        ),
        (
            f"LLM: provider={report.llm_provider}, timeout={report.llm_timeout_seconds}s, "
            f"allowed_action_tools={len(report.llm_allowed_action_tools)} [{', '.join(report.llm_allowed_action_tools) or 'none'}]"
        ),
        (
            f"SIS cfg: base_url_present={'yes' if report.sis_base_url_present else 'no'}, "
            f"api_key_present={'yes' if report.sis_api_key_present else 'no'}, "
            f"contract_check_enabled={report.sis_contract_check_enabled}"
        ),
    ]

    if report.sis_status == "disabled":
        lines.append("SIS runtime: disabled")
    elif report.sis_status == "ok":
        contract = "n/a"
        if report.sis_contract_ok is True:
            contract = "OK"
        elif report.sis_contract_ok is False:
            contract = "FAIL"
        latency = f" latency={report.sis_latency_ms}ms" if report.sis_latency_ms is not None else ""
        lines.append(f"SIS runtime: ping ✅{latency}, contract={contract}")
    elif report.sis_status == "degraded":
        latency = f" latency={report.sis_latency_ms}ms" if report.sis_latency_ms is not None else ""
        lines.append(f"SIS runtime: ping ⚠️{latency}, contract=FAIL ({report.sis_error_code or 'UNKNOWN'})")
    else:
        lines.append(f"SIS runtime: UNAVAILABLE ({report.sis_error_code or 'UNKNOWN'})")

    lines.append(
        f"SizeBot: check_enabled={report.sizebot_check_enabled}, base_url_present={'yes' if report.sizebot_base_url_present else 'no'}, "
        f"api_key_present={'yes' if report.sizebot_api_key_present else 'no'}, status={report.sizebot_status}"
    )
    suffix = f"Preflight: {report.preflight_status}; codes={preflight_codes}"
    if report.preflight_status == "FAIL":
        suffix += ". Fix env and restart."
    lines.append(suffix)
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
