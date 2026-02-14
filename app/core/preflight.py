from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PreflightItem:
    level: str
    code: str
    message: str
    hint: str


@dataclass(frozen=True)
class PreflightReport:
    ok: bool
    errors_count: int
    warnings_count: int
    items: list[PreflightItem] = field(default_factory=list)
    runtime_summary: dict[str, Any] = field(default_factory=dict)


def mask_secret(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "***"
    if len(raw) <= 4:
        return "***"
    return f"{raw[:3]}…{raw[-4:]}"


def _present(value: Any) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())


def preflight_validate_settings(
    settings: Any,
    *,
    effective_mode: str | None = None,
    runtime_override: str | None = None,
    redis_available_for_mode: bool = True,
) -> PreflightReport:
    items: list[PreflightItem] = []

    resolved_effective_mode = effective_mode or getattr(settings, "upstream_mode", "DEMO")

    if not _present(getattr(settings, "bot_token", "")):
        items.append(
            PreflightItem(
                level="ERROR",
                code="BOT_TOKEN_MISSING",
                message="BOT_TOKEN не задан.",
                hint="Укажи BOT_TOKEN в .env перед запуском бота.",
            )
        )

    if not getattr(settings, "owner_ids", []):
        items.append(
            PreflightItem(
                level="ERROR",
                code="OWNER_IDS_MISSING",
                message="OWNER_IDS пустой.",
                hint="Добавь хотя бы один Telegram user id в OWNER_IDS (CSV).",
            )
        )

    openai_key_present = _present(getattr(settings, "openai_api_key", None))
    if str(getattr(settings, "asr_provider", "")).lower() == "openai" and not openai_key_present:
        items.append(
            PreflightItem(
                level="ERROR",
                code="OPENAI_KEY_MISSING",
                message="ASR_PROVIDER=openai, но OPENAI_API_KEY отсутствует.",
                hint="Задай OPENAI_API_KEY или переключи ASR_PROVIDER=mock.",
            )
        )

    if str(getattr(settings, "llm_provider", "")).upper() == "OPENAI" and not openai_key_present:
        items.append(
            PreflightItem(
                level="ERROR",
                code="OPENAI_KEY_MISSING",
                message="LLM_PROVIDER=OPENAI, но OPENAI_API_KEY отсутствует.",
                hint="Задай OPENAI_API_KEY или отключи LLM_PROVIDER=OFF.",
            )
        )

    if getattr(settings, "asr_convert_voice_ogg_to_wav", False) and shutil.which("ffmpeg") is None:
        items.append(
            PreflightItem(
                level="ERROR",
                code="FFMPEG_MISSING",
                message="Включена конвертация ogg->wav, но ffmpeg не найден в PATH.",
                hint="Установи ffmpeg или выключи ASR_CONVERT_VOICE_OGG_TO_WAV.",
            )
        )

    if not redis_available_for_mode:
        items.append(
            PreflightItem(
                level="WARN",
                code="REDIS_UNAVAILABLE_FOR_PRECHECK",
                message="Redis недоступен для runtime override precheck.",
                hint="Проверь REDIS_URL/Redis; используется fallback на UPSTREAM_MODE.",
            )
        )

    if str(resolved_effective_mode).upper() in {"UPSTREAM", "SIS_HTTP"}:
        if not _present(getattr(settings, "sis_base_url", "")):
            items.append(
                PreflightItem(
                    level="ERROR",
                    code="SIS_BASE_URL_MISSING",
                    message="Для режима UPSTREAM не задан SIS_BASE_URL.",
                    hint="Укажи SIS_BASE_URL на API SIS.",
                )
            )
        if not _present(getattr(settings, "sis_ownerbot_api_key", "")):
            items.append(
                PreflightItem(
                    level="ERROR",
                    code="SIS_API_KEY_MISSING",
                    message="Для режима UPSTREAM не задан SIS_OWNERBOT_API_KEY.",
                    hint="Добавь SIS_OWNERBOT_API_KEY с правами OwnerBot в SIS.",
                )
            )

    if getattr(settings, "sizebot_check_enabled", False):
        if not _present(getattr(settings, "sizebot_base_url", "")):
            items.append(
                PreflightItem(
                    level="WARN",
                    code="SIZEBOT_BASE_URL_MISSING",
                    message="SizeBot check включён, но SIZEBOT_BASE_URL пустой.",
                    hint="Задай SIZEBOT_BASE_URL или отключи SIZEBOT_CHECK_ENABLED.",
                )
            )
        elif not _present(getattr(settings, "sizebot_api_key", "")):
            items.append(
                PreflightItem(
                    level="WARN",
                    code="SIZEBOT_API_KEY_MISSING",
                    message="SIZEBOT_BASE_URL задан, но SIZEBOT_API_KEY пустой.",
                    hint="Укажи SIZEBOT_API_KEY для авторизованных проверок.",
                )
            )

    errors_count = sum(1 for item in items if item.level == "ERROR")
    warnings_count = sum(1 for item in items if item.level == "WARN")
    return PreflightReport(
        ok=errors_count == 0,
        errors_count=errors_count,
        warnings_count=warnings_count,
        items=items,
        runtime_summary={
            "configured_mode": getattr(settings, "upstream_mode", "DEMO"),
            "effective_mode": resolved_effective_mode,
            "runtime_override": runtime_override,
            "asr_provider": getattr(settings, "asr_provider", ""),
            "llm_provider": getattr(settings, "llm_provider", ""),
            "openai_api_key_present": openai_key_present,
            "sis_base_url_present": _present(getattr(settings, "sis_base_url", "")),
            "sis_api_key_present": _present(getattr(settings, "sis_ownerbot_api_key", "")),
            "sizebot_base_url_present": _present(getattr(settings, "sizebot_base_url", "")),
            "sizebot_api_key_present": _present(getattr(settings, "sizebot_api_key", "")),
        },
    )


def format_preflight_report(report: PreflightReport) -> str:
    status = "OK" if report.ok else "FAIL"
    if report.ok and report.warnings_count:
        status = "WARN"
    lines = [f"preflight={status} errors={report.errors_count} warnings={report.warnings_count}"]
    for item in report.items[:5]:
        lines.append(f"- [{item.level}] {item.code}: {item.message} ({item.hint})")
    return "\n".join(lines)
