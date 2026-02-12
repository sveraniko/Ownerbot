from __future__ import annotations

from app.core.settings import Settings
from app.llm.provider_mock import MockPlanner
from app.llm.provider_openai import OpenAIPlanner
from app.llm.schema import LLMIntent
from app.tools.registry import ToolRegistry


async def llm_plan_intent(text: str, settings: Settings, registry: ToolRegistry) -> tuple[LLMIntent, str]:
    provider_name = settings.llm_provider.upper().strip()
    if provider_name == "OFF":
        return LLMIntent(tool=None, payload={}, error_message="Не понял запрос. /help", confidence=0.0), "OFF"
    if provider_name == "MOCK":
        provider = MockPlanner()
        provider_label = "MOCK"
    elif provider_name == "OPENAI":
        provider = OpenAIPlanner(settings)
        provider_label = "OPENAI"
    else:
        return LLMIntent(tool=None, payload={}, error_message="LLM провайдер не настроен", confidence=0.0), provider_name

    planned = await provider.plan(text)
    allowed_tools = {item["name"] for item in registry.list_tools()}
    allowed_tools.add("weekly_preset")
    if planned.tool is not None and planned.tool not in allowed_tools:
        return LLMIntent(tool=None, payload={}, error_message="LLM выбрал неизвестный tool", confidence=planned.confidence), provider_label

    if planned.tool is None:
        return planned, provider_label

    tool_def = registry.get(planned.tool)
    if tool_def and tool_def.kind == "action":
        allowed_actions = set(settings.llm_allowed_action_tools)
        if planned.tool not in allowed_actions:
            return LLMIntent(tool=None, payload={}, error_message="Action tool is not allowed", confidence=planned.confidence), provider_label
        payload = dict(planned.payload)
        payload["dry_run"] = True
        planned = planned.model_copy(update={"payload": payload})

    return planned, provider_label
