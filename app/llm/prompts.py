from __future__ import annotations

from pydantic import BaseModel

from app.tools.registry import ToolRegistry

BASE_LLM_INTENT_PROMPT = """
Ты — LLM-планировщик интента для OwnerBot.

ЖЁСТКИЕ ПРАВИЛА:
1) Ты НЕ генерируешь факты, цифры, отчёты или выводы по данным.
2) Ты только выбираешь один tool и формируешь payload/presentation.
3) Если запрос непонятен — верни tool=null и error_message на русском.
4) Один запрос = один intent. Никаких цепочек инструментов.
5) Для ACTION tools всегда возвращай payload.dry_run=true.
6) Для ACTION tools всегда возвращай idempotency_key (детерминированно из смысла запроса).
7) Если не уверен в выборе инструмента — верни tool=null и попроси уточнение.

ПРАВИЛА МАППИНГА:
- Запросы про недельный PDF-отчёт (weekly report/pdf) => tool="weekly_preset".
- Запросы вида "график выручки за N дней" => tool="revenue_trend", payload.days=N,
  presentation={"kind":"chart_png","days":N}.

ФОРМАТ ОТВЕТА: только JSON-объект структуры
{
  "tool": "<tool_name|weekly_preset|null>",
  "payload": {},
  "presentation": {} | null,
  "error_message": "..." | null,
  "confidence": 0..1
}

Язык error_message: русский.
""".strip()

LLM_INTENT_PROMPT = BASE_LLM_INTENT_PROMPT


def _payload_field_names(payload_model: type[BaseModel]) -> list[str]:
    fields = list(payload_model.model_fields.keys())
    if not fields:
        return []
    return fields[:8]


def build_tool_catalog_prompt(registry: ToolRegistry) -> str:
    lines: list[str] = ["ДОСТУПНЫЕ ИНСТРУМЕНТЫ:"]
    for tool in registry.list_definitions():
        fields = _payload_field_names(tool.payload_model)
        purpose = "action" if tool.kind == "action" else "read"
        fields_view = ", ".join(fields[:8]) if fields else "(без полей)"
        lines.append(f"- {tool.name}: {purpose}; payload: {fields_view}")
    lines.append("- weekly_preset: read; payload: (обычно пустой)")
    return "\n".join(lines)


def build_llm_intent_prompt(registry: ToolRegistry) -> str:
    return f"{BASE_LLM_INTENT_PROMPT}\n\n{build_tool_catalog_prompt(registry)}"
