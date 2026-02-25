from __future__ import annotations

import re
import uuid
from typing import Any

from app.agent_actions.param_coercion import coerce_action_payload
from app.agent_actions.plan_models import PlanIntent, PlanStep

_NOTIFY_TRIGGERS = ("сообщи команде", "пингани команду", "пингни команду", "напомни менеджеру", "оповести")


def _step_id(index: int) -> str:
    return f"s{index}"


def _step_tool(index: int, tool_name: str, payload: dict[str, Any], *, requires_confirm: bool = False, label: str | None = None) -> PlanStep:
    return PlanStep(step_id=_step_id(index), kind="TOOL", tool_name=tool_name, payload=payload, requires_confirm=requires_confirm, label=label)


def _step_notify(index: int, *, condition: str = "commit_succeeded", message_template: str = "", label: str = "Пинг команде") -> PlanStep:
    payload = {"message_template": message_template} if message_template else {}
    return PlanStep(
        step_id=_step_id(index),
        kind="NOTIFY_TEAM",
        tool_name="notify_team",
        payload=payload,
        requires_confirm=False,
        condition={"if": condition},
        label=label,
    )


def _has_notify_trigger(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _NOTIFY_TRIGGERS)


def _is_multi_commit_request(text: str) -> bool:
    lowered = text.lower()
    wants_coupon = any(token in lowered for token in ("купон", "скидк"))
    wants_reprice = any(token in lowered for token in ("репрайс", "обнови цены", "пересчитай цены"))
    wants_bump = any(token in lowered for token in ("подними цены", "снизь цены", "сделай +", "сделай -"))
    return sum(bool(flag) for flag in (wants_coupon, wants_reprice, wants_bump)) > 1


def _looks_like_fx_status_only(text: str) -> bool:
    lowered = text.lower()
    return ("проверь курс" in lowered or "какой сейчас курс" in lowered) and not any(
        token in lowered for token in ("обнови цены", "пересчитай цены", "репрайс", "если надо")
    )


def _looks_like_fx_if_needed(text: str) -> bool:
    lowered = text.lower()
    return "проверь курс" in lowered and any(token in lowered for token in ("если надо", "если нужно", "обнови цены", "пересчитай цены"))


def _extract_bump_payload(text: str) -> dict[str, Any]:
    candidate = coerce_action_payload("sis_prices_bump", {"value": text})
    return candidate.payload


def _extract_coupon_payload(text: str) -> dict[str, Any]:
    candidate = coerce_action_payload("create_coupon", {"percent_off": text, "hours_valid": text})
    return candidate.payload


def build_plan_from_text(text: str, actor, settings) -> PlanIntent | None:
    lowered = text.lower().strip()
    want_notify = _has_notify_trigger(lowered)

    if _is_multi_commit_request(lowered):
        return None

    if _looks_like_fx_status_only(lowered):
        return PlanIntent(
            plan_id=str(uuid.uuid4()),
            source="RULE_PHRASE_PACK",
            steps=[_step_tool(1, "sis_fx_status", {}, requires_confirm=False, label="FX статус")],
            summary="Проверка текущего FX-курса",
            confidence=0.95,
        )

    if _looks_like_fx_if_needed(lowered):
        steps: list[PlanStep] = [
            _step_tool(1, "sis_fx_status", {}, requires_confirm=False, label="FX статус"),
            _step_tool(2, "sis_fx_reprice_auto", {"dry_run": True, "refresh_snapshot": True}, requires_confirm=True, label="Репрайс FX"),
        ]
        if want_notify:
            steps.append(_step_notify(3, condition="commit_succeeded", label="Сообщение команде"))
        return PlanIntent(
            plan_id=str(uuid.uuid4()),
            source="RULE_PHRASE_PACK",
            steps=steps,
            summary="Проверка FX и репрайс при необходимости",
            confidence=0.96,
        )

    if any(token in lowered for token in ("rollback", "откатить последнее обновление цен", "откат цен")):
        return PlanIntent(
            plan_id=str(uuid.uuid4()),
            source="RULE_PHRASE_PACK",
            steps=[_step_tool(1, "sis_fx_rollback", {"dry_run": True}, requires_confirm=True, label="Откат FX")],
            summary="Откат последнего репрайса",
            confidence=0.9,
        )

    if any(token in lowered for token in ("купон", "скидк")):
        steps = [_step_tool(1, "create_coupon", _extract_coupon_payload(text), requires_confirm=True, label="Создать купон")]
        if want_notify:
            steps.append(_step_notify(2, condition="commit_succeeded", label="Сообщение команде"))
        return PlanIntent(
            plan_id=str(uuid.uuid4()),
            source="RULE_PHRASE_PACK",
            steps=steps,
            summary="Создание купона",
            confidence=0.9,
        )

    if any(token in lowered for token in ("подними цены", "снизь цены", "процент")):
        steps = [_step_tool(1, "sis_prices_bump", _extract_bump_payload(text), requires_confirm=True, label="Изменить цены")]
        if want_notify:
            steps.append(_step_notify(2, condition="commit_succeeded", label="Сообщение команде"))
        return PlanIntent(
            plan_id=str(uuid.uuid4()),
            source="RULE_PHRASE_PACK",
            steps=steps,
            summary="Изменение цен в процентах",
            confidence=0.9,
        )

    return None
