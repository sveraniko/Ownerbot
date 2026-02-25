from __future__ import annotations

from app.advice.classifier import AdviceTopic
from app.advice.data_brief import DataBriefResult
from app.advice.sanitizer import format_advice_text, synthesize_advice
from app.llm.schema import AdvicePayload, AdviceSuggestedTool


def test_synthesis_with_brief_adds_block_and_reduces_tools() -> None:
    advice = AdvicePayload(
        title="Совет",
        bullets=["Проверить цены"],
        experiments=["Сравнить окна"],
        suggested_tools=[
            AdviceSuggestedTool(tool="kpi_compare", payload={}),
            AdviceSuggestedTool(tool="revenue_trend", payload={}),
        ],
    )
    brief = DataBriefResult(
        created_at="2026-01-01T00:00:00+00:00",
        topic=AdviceTopic.PRICING_STRATEGY,
        tools_run=[{"tool": "kpi_compare", "ok": True, "warnings_count": 0}],
        facts={},
        summary="Тема: PRICING_STRATEGY\nKPI: net A=1 vs B=2",
        warnings=[],
    )

    out = synthesize_advice(topic=AdviceTopic.PRICING_STRATEGY.value, question_text="q", advice=advice, brief=brief)
    assert [item.tool for item in out.suggested_tools] == ["revenue_trend"]

    text = format_advice_text(out, "🧭 medium", [], brief=brief)
    assert "📌 Data Brief" in text
    assert "data brief attached" in text
