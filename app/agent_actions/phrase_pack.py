from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from app.agent_actions.param_coercion import parse_hours_value, parse_ids_value, parse_order_id_value, parse_percent_value


@dataclass(frozen=True)
class ActionIntentCandidate:
    tool_name: str
    payload_partial: dict[str, Any]
    missing_fields_hint: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionPhraseRule:
    id: str
    tool_name: str
    patterns: tuple[str, ...]
    param_extractors: tuple[Callable[[str], dict[str, Any]], ...] = ()
    defaults: dict[str, Any] | None = None
    priority: int = 100


def _extract_percent(text: str) -> dict[str, Any]:
    lowered = text.lower()
    sign = -1.0 if any(token in lowered for token in ("минус", "сниз", "убав", "-") if token.strip()) else 1.0
    match = re.search(r"(\d{1,2}(?:[\.,]\d+)?)\s*%", lowered)
    if not match:
        match = re.search(r"(?:на|\+|-)\s*(\d{1,2}(?:[\.,]\d+)?)\s*(?:проц|percent)", lowered)
    if not match:
        return {}
    value = parse_percent_value(match.group(1))
    if value is None:
        return {}
    return {"value": value * sign, "percent_off": abs(value)}


def _extract_hours(text: str) -> dict[str, Any]:
    match = re.search(r"на\s+([^\n]+)$", text.lower())
    candidate = match.group(1) if match else text
    hours = parse_hours_value(candidate)
    return {"hours_valid": hours} if hours else {}


def _extract_order_id(text: str) -> dict[str, Any]:
    match = re.search(r"(?:заказ|order)\s+([\w-]+)", text, flags=re.IGNORECASE)
    if match:
        order_id = parse_order_id_value(match.group(1))
        if order_id:
            return {"order_id": order_id}
    order_id = parse_order_id_value(text)
    return {"order_id": order_id} if order_id else {}


def _extract_product_ids(text: str) -> dict[str, Any]:
    match = re.search(r"(?:товар(?:ы)?|id)\s+(.+)$", text, flags=re.IGNORECASE)
    source = match.group(1) if match else text
    ids = parse_ids_value(source)
    return {"product_ids": ids} if ids else {}


def _extract_look_ids(text: str) -> dict[str, Any]:
    match = re.search(r"(?:лук(?:и)?|look(?:s)?|id)\s+(.+)$", text, flags=re.IGNORECASE)
    source = match.group(1) if match else text
    ids = parse_ids_value(source)
    return {"look_ids": ids} if ids else {}


def _extract_notify_message(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^(пинг|напомни|сообщи)\s*(менеджеру|команде)?", "", text, flags=re.IGNORECASE).strip(" -—:\t")
    return {"message": cleaned} if cleaned else {}


def _extract_coupon_code(text: str) -> dict[str, Any]:
    match = re.search(r"(?:купон\s+)([a-z0-9_-]+)", text, flags=re.IGNORECASE)
    if not match:
        return {}
    return {"code": match.group(1).upper()}


RULES: tuple[ActionPhraseRule, ...] = (
    ActionPhraseRule(
        id="fx_status",
        tool_name="sis_fx_status",
        patterns=(r"\b(проверь курс|какой сейчас курс|что по курсу|fx статус|курс валют)\b",),
        priority=5,
    ),
    ActionPhraseRule(
        id="fx_reprice",
        tool_name="sis_fx_reprice_auto",
        patterns=(r"\b(репрайс|пересчитай цены|обнови цены по курсу|fx apply|если надо обнови цены)\b",),
        defaults={"refresh_snapshot": True, "force": False},
        priority=10,
    ),
    ActionPhraseRule(
        id="fx_rollback",
        tool_name="sis_fx_rollback",
        patterns=(r"\b(rollback цен|откатить последнее обновление цен|откат цен)\b",),
        priority=12,
    ),
    ActionPhraseRule(
        id="prices_bump",
        tool_name="sis_prices_bump",
        patterns=(r"\b(подними цены|снизь цены|сделай\s*[+-]?\d+)\b",),
        param_extractors=(_extract_percent,),
        priority=20,
    ),
    ActionPhraseRule(
        id="coupon_create",
        tool_name="create_coupon",
        patterns=(r"\b(купон|скидка|создай купон)\b",),
        param_extractors=(_extract_percent, _extract_hours),
        priority=30,
    ),
    ActionPhraseRule(
        id="coupon_disable",
        tool_name="create_coupon",
        patterns=(r"\b(выключи купон|отключи купон)\b",),
        param_extractors=(_extract_coupon_code,),
        defaults={"disable": True},
        priority=31,
    ),
    ActionPhraseRule(
        id="notify_team",
        tool_name="notify_team",
        patterns=(r"\b(пинг менеджеру|напомни по заказу|сообщи команде|пингни команду)\b",),
        param_extractors=(_extract_order_id, _extract_notify_message),
        priority=40,
    ),
    ActionPhraseRule(
        id="products_publish",
        tool_name="sis_products_publish",
        patterns=(r"\b(опубликуй товары|скрой товары|архивируй товары)\b",),
        param_extractors=(_extract_product_ids,),
        defaults={"target_status": "ACTIVE"},
        priority=50,
    ),
    ActionPhraseRule(
        id="looks_publish",
        tool_name="sis_looks_publish",
        patterns=(r"\b(опубликуй луки|скрой луки|архивируй луки)\b",),
        param_extractors=(_extract_look_ids,),
        defaults={"target_active": True},
        priority=60,
    ),
    ActionPhraseRule(
        id="discounts_set",
        tool_name="sis_discounts_set",
        patterns=(r"\b(поставь скидку)\b",),
        param_extractors=(_extract_product_ids, _extract_percent),
        priority=70,
    ),
    ActionPhraseRule(
        id="discounts_clear",
        tool_name="sis_discounts_clear",
        patterns=(r"\b(убери скидки|очисти скидки)\b",),
        param_extractors=(_extract_product_ids,),
        priority=71,
    ),
)


def _apply_overrides(rule: ActionPhraseRule, text: str, payload: dict[str, Any]) -> None:
    lowered = text.lower()
    if rule.tool_name == "sis_products_publish" and any(token in lowered for token in ("скрой", "архив")):
        payload["target_status"] = "ARCHIVED"
    if rule.tool_name == "sis_looks_publish" and any(token in lowered for token in ("скрой", "архив")):
        payload["target_active"] = False
    if rule.tool_name == "sis_fx_reprice_auto" and any(token in lowered for token in ("форс", "принуд")):
        payload["force"] = True


def _missing_hints(tool_name: str, payload: dict[str, Any]) -> tuple[str, ...]:
    if tool_name == "sis_prices_bump" and payload.get("value") is None:
        return ("процент изменения цены",)
    if tool_name == "create_coupon":
        if payload.get("disable"):
            return () if payload.get("code") else ("код купона",)
        missing = []
        if payload.get("percent_off") is None:
            missing.append("размер скидки в %")
        if payload.get("hours_valid") is None:
            missing.append("срок действия в часах")
        return tuple(missing)
    if tool_name == "notify_team" and not payload.get("message") and not payload.get("order_id"):
        return ("сообщение для менеджера",)
    if tool_name in {"sis_products_publish", "sis_discounts_set", "sis_discounts_clear"} and not payload.get("product_ids"):
        return ("список product_ids",)
    if tool_name == "sis_looks_publish" and not payload.get("look_ids"):
        return ("список look_ids",)
    return ()


def match_action_phrase(text: str) -> ActionIntentCandidate | None:
    normalized = text.strip().lower()
    for rule in sorted(RULES, key=lambda item: item.priority):
        if not any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in rule.patterns):
            continue
        payload = dict(rule.defaults or {})
        for extractor in rule.param_extractors:
            payload.update(extractor(text))
        _apply_overrides(rule, text, payload)
        return ActionIntentCandidate(
            tool_name=rule.tool_name,
            payload_partial=payload,
            missing_fields_hint=_missing_hints(rule.tool_name, payload),
        )
    return None
