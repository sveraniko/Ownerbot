from __future__ import annotations

from app.tools.contracts import ToolDefinition, ToolResponse


def format_tool_response(resp: ToolResponse) -> str:
    if resp.status == "error" and resp.error:
        return f"Ошибка: {resp.error.code}\n{resp.error.message}"

    lines = ["Суть:", "Запрос выполнен."]
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
        f"Mode: {status.get('mode', 'unknown')}\n\n"
        "Примеры:\n"
        "• дай KPI за вчера\n"
        "• что с заказами, что зависло\n"
        "• покажи последние 7 дней выручку\n"
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
