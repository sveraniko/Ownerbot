from __future__ import annotations

import uuid
from typing import Any

from app.agent_actions.param_coercion import coerce_action_payload
from app.agent_actions.plan_models import PlanIntent, PlanStep

_NOTIFY_TRIGGERS = ("сообщи команде", "пингани команду", "напомни менеджеру", "оповести")
_FX_PATTERNS = ("проверь курс", "обнови цены если нужно", "если надо обнови цены")
_COUPON_PATTERNS = ("создай купон", "скидка", "купон")


def _has_notify_trigger(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _NOTIFY_TRIGGERS)


def _step_tool(tool_name: str, payload: dict[str, Any], *, requires_confirm: bool = True) -> PlanStep:
    return PlanStep(step_id="s1", kind="TOOL", tool_name=tool_name, payload=payload, requires_confirm=requires_confirm)


def _step_notify(message_template: str = "") -> PlanStep:
    payload = {"message_template": message_template} if message_template else {}
    return PlanStep(step_id="s2", kind="NOTIFY_TEAM", tool_name="notify_team", payload=payload, requires_confirm=False, condition={"if": "commit_succeeded"})


def build_plan_from_text(text: str, actor, settings) -> PlanIntent | None:
    lowered = text.lower().strip()
    want_notify = _has_notify_trigger(lowered)

    if any(pattern in lowered for pattern in _FX_PATTERNS):
        step1 = _step_tool("sis_fx_reprice_auto", {"dry_run": True, "refresh_snapshot": True})
        steps = [step1]
        if want_notify:
            steps.append(_step_notify())
        return PlanIntent(
            plan_id=str(uuid.uuid4()),
            source="RULE_PHRASE_PACK",
            steps=steps,
            summary="Проверка FX и обновление цен при необходимости",
            confidence=0.95,
        )

    if any(pattern in lowered for pattern in _COUPON_PATTERNS):
        candidate = coerce_action_payload("create_coupon", {"percent_off": text, "hours_valid": text})
        step1 = _step_tool("create_coupon", candidate.payload)
        steps = [step1]
        if want_notify:
            steps.append(_step_notify())
        return PlanIntent(
            plan_id=str(uuid.uuid4()),
            source="RULE_PHRASE_PACK",
            steps=steps,
            summary="Создание купона и оповещение команды",
            confidence=0.9,
        )

    return None
