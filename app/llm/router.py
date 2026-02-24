from __future__ import annotations

import hashlib
import json

from app.core.settings import Settings
from app.llm.provider_mock import MockPlanner
from app.llm.provider_openai import OpenAIPlanner
from app.llm.prompts import build_llm_intent_prompt
from app.llm.schema import LLMIntent
from app.tools.registry import ToolRegistry


def _deterministic_idempotency_key(tool_name: str, payload: dict, text: str) -> str:
    source = {
        "tool": tool_name,
        "text": text.strip().lower(),
        "payload": {k: v for k, v in payload.items() if k != "idempotency_key"},
    }
    digest = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"llm-{digest[:32]}"


async def llm_plan_intent(text: str, settings: Settings, registry: ToolRegistry) -> tuple[LLMIntent, str]:
    provider_name = settings.llm_provider.upper().strip()
    if provider_name == "OFF":
        return LLMIntent(intent_kind="UNKNOWN", tool=None, payload={}, error_message="Не понял запрос. /help", confidence=0.0), "OFF"
    if provider_name == "MOCK":
        provider = MockPlanner()
        provider_label = "MOCK"
    elif provider_name == "OPENAI":
        provider = OpenAIPlanner(settings)
        provider_label = "OPENAI"
    else:
        return LLMIntent(intent_kind="UNKNOWN", tool=None, payload={}, error_message="LLM провайдер не настроен", confidence=0.0), provider_name

    prompt = build_llm_intent_prompt(registry)
    planned = await provider.plan(text, prompt=prompt)

    if planned.intent_kind in {"ADVICE", "UNKNOWN"}:
        return planned, provider_label

    allowed_tools = {item["name"] for item in registry.list_tools()}
    allowed_tools.add("weekly_preset")
    if planned.tool is not None and planned.tool not in allowed_tools:
        return (
            LLMIntent(intent_kind="UNKNOWN", tool=None, payload={}, error_message="LLM выбрал неизвестный tool", confidence=planned.confidence),
            provider_label,
        )

    if planned.tool is None:
        return LLMIntent(intent_kind="UNKNOWN", tool=None, payload={}, error_message="Не понял запрос. /help", confidence=planned.confidence), provider_label

    tool_def = registry.get(planned.tool)
    tool_kind = "action" if tool_def and tool_def.kind == "action" else "report"
    planned = planned.model_copy(update={"tool_source": "LLM", "tool_kind": tool_kind})
    if tool_def and tool_def.kind == "action":
        allowed_actions = set(settings.llm_allowed_action_tools)
        if planned.tool not in allowed_actions:
            return (
                LLMIntent(intent_kind="UNKNOWN", tool=None, payload={}, error_message="Action tool is not allowed", confidence=planned.confidence),
                provider_label,
            )
        payload = dict(planned.payload)
        payload["dry_run"] = True
        payload["idempotency_key"] = _deterministic_idempotency_key(planned.tool, payload, text)
        planned = planned.model_copy(update={"payload": payload})

    return planned, provider_label
