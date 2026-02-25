from __future__ import annotations

import json

import pytest

from app.retro.service import FunnelReport, RetroGaps, RetroGapsWithDeltas, RetroSummary, RetroSummaryWithDeltas
from app.tools.impl import retro_export, retro_gaps, retro_summary


@pytest.mark.asyncio
async def test_retro_summary_tool_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _summary(_session, _days):
        base = RetroSummary(
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
        return RetroSummaryWithDeltas(current=base, previous=base, deltas={"advice_total_delta": {"absolute": 0, "percent": None}})

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(retro_summary, "retro_summary_with_deltas", _summary)
    monkeypatch.setattr(retro_summary, "write_audit_event", _noop)

    response = await retro_summary.handle(retro_summary.Payload(period_days=7), "corr", session=None)
    assert response.status == "ok"
    assert response.data["text"]
    assert "deltas" in response.data


@pytest.mark.asyncio
async def test_retro_tools_reject_invalid_period(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(retro_gaps, "write_audit_event", _noop)
    response = await retro_gaps.handle(retro_gaps.Payload(period_days=15), "corr", session=None)
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_retro_export_artifact_and_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _summary(_session, _days):
        current = RetroSummary(
            period_days=7,
            totals={
                "intents_total": 1,
                "advice_total": 1,
                "tool_calls_total": 0,
                "plans_previewed_total": 0,
                "plans_committed_total": 0,
                "memos_generated_total": 1,
                "briefs_built_total": 1,
            },
            routing={"rule_hits_total": 1, "llm_plans_total": 0, "llm_fallback_rate": 0.0},
            top_tools=[{"tool_name": "tool@example.com", "count": 1}],
            quality={
                "confidence_counts": {"TOOL": {"high": 0, "med": 0, "low": 0}, "ADVICE": {"high": 1, "med": 0, "low": 0}},
                "top_warning_codes": [{"warning": "call +12345678901", "count": 1}],
            },
            failures={"unknown_total": 0, "top_unknown_reasons": []},
        )
        return RetroSummaryWithDeltas(current=current, previous=current, deltas={})

    async def _gaps(_session, _days):
        base = RetroGaps(period_days=7, top_unimplemented_tools=[], top_disallowed_actions=[], top_missing_params=[])
        return RetroGapsWithDeltas(current=base, previous=base, deltas={})

    async def _funnels(_session, _days):
        return FunnelReport(period_days=7, plan={"built": 1}, advice={"memo": 1}, confidence="high", notes=["mail me at me@example.com"])

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(retro_export, "retro_summary_with_deltas", _summary)
    monkeypatch.setattr(retro_export, "retro_gaps_with_deltas", _gaps)
    monkeypatch.setattr(retro_export, "retro_funnels", _funnels)
    monkeypatch.setattr(retro_export, "write_audit_event", _noop)

    response = await retro_export.handle(retro_export.Payload(period_days=7), "corr", session=None)
    assert response.status == "ok"
    assert response.artifacts
    payload = json.loads(response.artifacts[0].content.decode("utf-8"))
    assert {"period_days", "generated_at", "summary", "gaps", "funnels"}.issubset(payload.keys())
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "tool@example.com" not in dumped
    assert "me@example.com" not in dumped
    assert "+12345678901" not in dumped
