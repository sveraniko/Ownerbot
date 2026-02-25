from __future__ import annotations

import pytest

from app.retro.service import RetroGaps, RetroSummary
from app.tools.impl import retro_gaps, retro_summary


@pytest.mark.asyncio
async def test_retro_summary_tool_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _summary(_session, _days):
        return RetroSummary(
            period_days=7,
            totals={
                "intents_total": 1,
                "advice_total": 0,
                "tool_calls_total": 0,
                "plans_previewed_total": 0,
                "plans_committed_total": 0,
                "memos_generated_total": 0,
                "briefs_built_total": 0,
            },
            routing={"rule_hits_total": 1, "llm_plans_total": 0, "llm_fallback_rate": 0.0},
            top_tools=[],
            quality={
                "confidence_counts": {"TOOL": {"high": 0, "med": 0, "low": 0}, "ADVICE": {"high": 0, "med": 0, "low": 0}},
                "top_warning_codes": [],
            },
            failures={"unknown_total": 0, "top_unknown_reasons": []},
        )

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(retro_summary, "retro_summary", _summary)
    monkeypatch.setattr(retro_summary, "write_audit_event", _noop)

    response = await retro_summary.handle(retro_summary.Payload(period_days=7), "corr", session=None)
    assert response.status == "ok"
    assert response.data["text"]


@pytest.mark.asyncio
async def test_retro_tools_reject_invalid_period(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(retro_gaps, "write_audit_event", _noop)
    response = await retro_gaps.handle(retro_gaps.Payload(period_days=15), "corr", session=None)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "VALIDATION_ERROR"
