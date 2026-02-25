from __future__ import annotations

from app.retro.formatter import format_retro_gaps, format_retro_summary
from app.retro.service import RetroGaps, RetroSummary


def test_format_retro_summary_contains_sections() -> None:
    summary = RetroSummary(
        period_days=7,
        totals={
            "intents_total": 10,
            "advice_total": 3,
            "tool_calls_total": 4,
            "plans_previewed_total": 2,
            "plans_committed_total": 1,
            "memos_generated_total": 1,
            "briefs_built_total": 1,
        },
        routing={"rule_hits_total": 6, "llm_plans_total": 4, "llm_fallback_rate": 0.4},
        top_tools=[{"tool_name": "sis_fx_status", "count": 2}],
        quality={
            "confidence_counts": {
                "TOOL": {"high": 1, "med": 2, "low": 0},
                "ADVICE": {"high": 1, "med": 1, "low": 0},
            },
            "top_warning_codes": [{"warning": "no_data", "count": 2}],
        },
        failures={"unknown_total": 1, "top_unknown_reasons": [{"reason": "no_match", "count": 1}]},
    )

    text = format_retro_summary(summary)

    assert "📊 Usage" in text
    assert "🧭 Routing" in text
    assert "🧪 Quality" in text
    assert "⚠️ Failures" in text
    assert "🧰 Top tools" in text


def test_format_retro_gaps_empty_dataset() -> None:
    gaps = RetroGaps(period_days=30, top_unimplemented_tools=[], top_disallowed_actions=[], top_missing_params=[])
    text = format_retro_gaps(gaps)
    assert "нет данных" in text
    assert "что делать" in text
