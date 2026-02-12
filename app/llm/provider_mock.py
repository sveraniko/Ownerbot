from __future__ import annotations

from app.llm.schema import LLMIntent


class MockPlanner:
    async def plan(self, text: str) -> LLMIntent:
        normalized = text.lower().strip()
        if "недель" in normalized and "pdf" in normalized:
            return LLMIntent(tool="weekly_preset", payload={}, confidence=0.98)
        if "график" in normalized and "14" in normalized and ("выруч" in normalized or "продаж" in normalized):
            return LLMIntent(
                tool="revenue_trend",
                payload={"days": 14},
                presentation={"kind": "chart_png", "days": 14},
                confidence=0.96,
            )
        if "завис" in normalized and "заказ" in normalized and "3" in normalized:
            return LLMIntent(tool="orders_search", payload={"status": "stuck", "days": 3}, confidence=0.88)
        if "уведом" in normalized and "команд" in normalized:
            msg = text.split(":", maxsplit=1)[1].strip() if ":" in text else text
            return LLMIntent(tool="notify_team", payload={"message": msg, "dry_run": True}, confidence=0.91)
        return LLMIntent(tool=None, payload={}, error_message="Не понял запрос. /help", confidence=0.1)
