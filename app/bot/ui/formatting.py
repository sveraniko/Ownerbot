from __future__ import annotations

from app.tools.contracts import ToolDefinition, ToolResponse


SIS_SOURCE_TAG = "SIS(ownerbot/v1)"
DEMO_SOURCE_TAG = "DEMO"


def detect_source_tag(resp: ToolResponse) -> str | None:
    sources = resp.provenance.sources if resp.provenance else []
    joined = " ".join(sources).lower()
    if "ownerbot/v1" in joined or "sis" in joined:
        return SIS_SOURCE_TAG
    if "local_demo" in joined or "ownerbot_demo" in joined:
        return DEMO_SOURCE_TAG
    return None


def format_tool_response(resp: ToolResponse, *, source_tag: str | None = None) -> str:
    if resp.status == "error" and resp.error:
        return f"Ошибка: {resp.error.code}\n{resp.error.message}"

    lines = []
    resolved_source = source_tag or detect_source_tag(resp)
    if resolved_source:
        lines.append(f"Источник: {resolved_source}")
    lines.extend(["Суть:", "Запрос выполнен."])
    if resp.data:
        lines.append("\nЦифры:")
        for key, value in resp.data.items():
            lines.append(f"• {key}: {value}")

    if resp.provenance:
        lines.append("\nProvenance:")
        if resp.provenance.sources:
            for source in resp.provenance.sources:
                lines.append(f"• {source}")
        else:
            lines.append("• (none)")

    if resp.warnings:
        lines.append("\nWarnings:")
        for warning in resp.warnings:
            lines.append(f"• {warning.code}: {warning.message}")

    return "\n".join(lines)


def format_start_message(status: dict) -> str:
    return (
        "OwnerBot online.\n\n"
        f"DB: {'ok' if status.get('db_ok') else 'fail'}\n"
        f"Redis: {'ok' if status.get('redis_ok') else 'fail'}\n"
        f"Owner IDs: {status.get('owner_ids_text', 'none')}\n"
        f"Upstream: configured={status.get('configured_mode', 'unknown')}, effective={status.get('effective_mode', 'unknown')}\n"
        f"ASR={status.get('asr_provider', 'unknown')} | LLM={status.get('llm_provider', 'unknown')}\n"
        "Подробнее: /systems\n\n"
        "Примеры:\n"
        "• дай KPI за вчера\n"
        "• что с заказами, что зависло\n"
        "• /trend 14\n"
        "• график выручки 7 дней\n"
        "• /weekly_pdf\n"
        "• флагни заказ OB-1003 причина тест\n"
        "• /notify Проверь зависшие заказы и ответь клиентам\n"
        "• уведомь команду: проверь OB-1003, завис\n"
    )


def format_tools_list(tools: list[ToolDefinition]) -> str:
    lines = ["Tools:"]
    for tool in tools:
        status = "stub" if tool.is_stub else "ok"
        lines.append(f"• {tool.name} v{tool.version} ({status})")
    return "\n".join(lines)
