from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class IntentResult:
    tool: str | None
    payload: dict
    error_message: str | None = None


def extract_order_id(text: str) -> str | None:
    match = re.search(r"\bob-\d+\b", text, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def extract_days(text: str) -> int | None:
    match = re.search(r"(\d{1,2})\s*(?:дней|дня|дн)", text.lower())
    if not match:
        return None
    days = int(match.group(1))
    return days if 1 <= days <= 60 else None


def extract_reason_after_keywords(text: str, keywords: list[str] | None = None) -> str:
    keywords = keywords or ["причина", "reason"]
    for keyword in keywords:
        match = re.search(rf"\b{re.escape(keyword)}\b\s*(.+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def route_intent(text: str) -> IntentResult:
    normalized = text.lower().strip()

    # 1) notify_team
    if normalized.startswith("/notify"):
        message = re.sub(r"^/notify(?:@\w+)?\s*", "", text, flags=re.IGNORECASE).strip()
        return IntentResult(tool="notify_team", payload={"message": message, "dry_run": True})

    notify_phrases = ["уведомь команду", "сообщи менеджеру", "пни менеджера"]
    for phrase in notify_phrases:
        index = normalized.find(phrase)
        if index != -1:
            message = text[index + len(phrase) :].strip().lstrip(" -—:\t").strip()
            return IntentResult(tool="notify_team", payload={"message": message, "dry_run": True})

    # 2) flag_order
    flag_keywords = ["флаг", "пометь", "отметь", "flag"]
    order_id = extract_order_id(text)
    if order_id and any(keyword in normalized for keyword in flag_keywords):
        reason = extract_reason_after_keywords(text)
        if not reason:
            order_match = re.search(r"\bob-\d+\b", text, flags=re.IGNORECASE)
            if order_match:
                reason = text[order_match.end() :].strip().lstrip(" -—:\t").strip()
        payload = {"order_id": order_id, "dry_run": True}
        if reason:
            payload["reason"] = reason
        return IntentResult(tool="flag_order", payload=payload)

    # 3) order_detail
    order_detail_match = re.search(r"\b(?:заказ|order)\s*(ob-\d+)\b", text, flags=re.IGNORECASE)
    if order_detail_match:
        return IntentResult(tool="order_detail", payload={"order_id": order_detail_match.group(1).upper()})

    # 4) revenue_trend
    days = extract_days(text)
    if days and any(word in normalized for word in ["выруч", "продаж"]):
        return IntentResult(tool="revenue_trend", payload={"days": days})

    # 5) chats_unanswered
    if any(word in normalized for word in ["чаты", "чат", "без ответа", "не отвечено", "не отвеч"]):
        return IntentResult(tool="chats_unanswered", payload={"limit": 10})

    # 6) orders_search
    if any(word in normalized for word in ["заказы", "завис", "неоплач"]):
        payload = {}
        if "завис" in normalized or "неоплач" in normalized:
            payload["status"] = "stuck"
        return IntentResult(tool="orders_search", payload=payload)

    # 7) kpi_snapshot
    if any(word in normalized for word in ["kpi", "выруч", "продаж", "вчера", "сегодня"]):
        payload: dict = {}
        if "вчера" in normalized:
            payload["day"] = (date.today() - timedelta(days=1)).isoformat()
        return IntentResult(tool="kpi_snapshot", payload=payload)

    return IntentResult(tool=None, payload={}, error_message="Не понял запрос. /help")
