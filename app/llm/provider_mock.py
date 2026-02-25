from __future__ import annotations

from app.llm.schema import AdvicePayload, AdviceSuggestedAction, AdviceSuggestedTool, LLMIntent


class MockPlanner:
    async def plan(self, text: str, prompt: str = "") -> LLMIntent:
        normalized = text.lower().strip()
        if "недель" in normalized and "pdf" in normalized:
            return LLMIntent(intent_kind="TOOL", tool="weekly_preset", payload={}, confidence=0.98)
        if "график" in normalized and "14" in normalized and ("выруч" in normalized or "продаж" in normalized):
            return LLMIntent(
                intent_kind="TOOL",
                tool="revenue_trend",
                payload={"days": 14},
                presentation={"kind": "chart_png", "days": 14},
                confidence=0.96,
            )
        if "завис" in normalized and "заказ" in normalized and "3" in normalized:
            return LLMIntent(intent_kind="TOOL", tool="orders_search", payload={"status": "stuck", "days": 3}, confidence=0.88)
        if "уведом" in normalized and "команд" in normalized:
            msg = text.split(":", maxsplit=1)[1].strip() if ":" in text else text
            return LLMIntent(intent_kind="TOOL", tool="notify_team", payload={"message": msg, "dry_run": True}, confidence=0.91)
        if "гипотез" in normalized or "что попробовать" in normalized:
            return LLMIntent(
                intent_kind="ADVICE",
                advice=AdvicePayload(
                    title="Гипотезы роста",
                    bullets=["Проверьте влияние канала трафика и цены предложения."],
                    risks=["Без проверки данных гипотеза может быть ложной."],
                    experiments=["Сравнить конверсию по каналам за 7 дней и 30 дней."],
                    suggested_tools=[AdviceSuggestedTool(tool="kpi_snapshot", payload={"window": "7d"})],
                    suggested_actions=[AdviceSuggestedAction(label="Подготовить купон (preview)", tool="create_coupon", payload_partial={"dry_run": True, "percent_off": 10}, why="Тест на конверсию")],
                ),
                confidence=0.74,
            )
        return LLMIntent(intent_kind="UNKNOWN", tool=None, payload={}, error_message="Не понял запрос. /help", confidence=0.1)
