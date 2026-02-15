from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class IntentResult:
    tool: str | None
    payload: dict
    presentation: dict | None = None
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

    trend_command_match = re.match(r"^/trend(?:@\w+)?(?:\s+(\d{1,2}))?\s*$", text.strip(), flags=re.IGNORECASE)
    if trend_command_match:
        raw_days = trend_command_match.group(1)
        days = int(raw_days) if raw_days else 14
        if 1 <= days <= 60:
            return IntentResult(
                tool="revenue_trend",
                payload={"days": days},
                presentation={"kind": "chart_png", "days": days},
            )
        return IntentResult(tool=None, payload={}, error_message="/trend: укажи число дней от 1 до 60.")

    weekly_pdf_command_match = re.match(r"^/weekly_pdf(?:@\w+)?\s*$", text.strip(), flags=re.IGNORECASE)
    if weekly_pdf_command_match:
        return IntentResult(tool="kpi_snapshot", payload={}, presentation={"kind": "weekly_pdf"})

    if "дай дашборд" in normalized or "отчет за сегодня" in normalized or "отчёт за сегодня" in normalized:
        return IntentResult(tool="biz_dashboard_daily", payload={"format": "png"})

    if "еженедельный отчет" in normalized or "еженедельный отчёт" in normalized:
        return IntentResult(tool="biz_dashboard_weekly", payload={"format": "pdf"})

    ops_report_phrases = ["операционный отчет", "операционный отчёт", "ops отчет", "ops отчёт", "отчет по проблемам", "отчёт по проблемам", "что горит"]
    if any(phrase in normalized for phrase in ops_report_phrases):
        return IntentResult(tool="biz_dashboard_ops", payload={"format": "pdf", "tz": "Europe/Berlin"})

    fx_status_phrases = ["fx статус", "что по курсу", "курс валют"]
    if "курс" in normalized or any(phrase in normalized for phrase in fx_status_phrases):
        return IntentResult(tool="sis_fx_status", payload={})

    if "обнови цены принудительно" in normalized or "форс пересчет" in normalized:
        return IntentResult(tool="sis_fx_reprice_auto", payload={"dry_run": True, "force": True, "refresh_snapshot": True})

    if "обнови цены" in normalized or "пересчитай цены" in normalized or "fx пересчет" in normalized:
        return IntentResult(tool="sis_fx_reprice_auto", payload={"dry_run": True, "force": False, "refresh_snapshot": True})

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
    trend_phrases = ["график выручки", "график продаж", "покажи график продаж", "покажи график выручки"]
    if days and (
        any(phrase in normalized for phrase in trend_phrases)
        or ("график" in normalized and any(word in normalized for word in ["выруч", "продаж"]))
    ):
        return IntentResult(
            tool="revenue_trend",
            payload={"days": days},
            presentation={"kind": "chart_png", "days": days},
        )


    forecast_demand_phrases = ["прогноз спроса", "прогноз на 7 дней", "что будет продаваться"]
    if any(phrase in normalized for phrase in forecast_demand_phrases):
        return IntentResult(tool="demand_forecast", payload={"horizon_days": 7})

    reorder_plan_phrases = ["план закупки", "план дозакупки", "что докупить"]
    if any(phrase in normalized for phrase in reorder_plan_phrases):
        return IntentResult(tool="reorder_plan", payload={"lead_time_days": 14, "safety_stock_days": 7, "horizon_days": 14})

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
