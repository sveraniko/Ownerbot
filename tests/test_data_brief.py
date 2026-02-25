from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.advice.classifier import AdviceTopic
from app.advice.data_brief import (
    DataBriefResult,
    ToolCallSpec,
    is_cooldown_active,
    load_cached_brief,
    run_tool_set_sequential,
    save_brief_cache,
    select_tool_set,
    set_brief_cooldown,
)
from app.tools.contracts import ToolError, ToolProvenance, ToolResponse
from app.tools.registry_setup import build_registry


def test_data_brief_toolset_selection_report_only() -> None:
    registry = build_registry()
    for topic in [
        AdviceTopic.SEASON_TRENDS,
        AdviceTopic.PROMO_STRATEGY,
        AdviceTopic.PRICING_STRATEGY,
        AdviceTopic.ASSORTMENT_STRATEGY,
        AdviceTopic.OPS_PRIORITY,
        AdviceTopic.GROWTH_PLAN,
    ]:
        calls = select_tool_set(topic)
        assert 2 <= len(calls) <= 4
        assert all((registry.get(call.tool) is not None and registry.get(call.tool).kind != "action") for call in calls)


@pytest.mark.asyncio
async def test_data_brief_caching_and_cooldown(monkeypatch) -> None:
    from app.advice import data_brief

    class _Redis:
        def __init__(self) -> None:
            self.store = {}

        async def get(self, key):
            return self.store.get(key)

        async def set(self, key, value, ex=None):
            self.store[key] = value
            return True

    redis = _Redis()

    async def _get_redis():
        return redis

    monkeypatch.setattr(data_brief, "get_redis", _get_redis)

    brief = DataBriefResult(
        created_at="2026-01-01T00:00:00+00:00",
        topic=AdviceTopic.PRICING_STRATEGY,
        tools_run=[{"tool": "sis_fx_status", "ok": True, "warnings_count": 0}],
        facts={"fx": {"latest_rate": 0.93}},
        summary="ok",
        warnings=[],
    )
    await save_brief_cache(10, brief)
    loaded = await load_cached_brief(10, AdviceTopic.PRICING_STRATEGY)
    assert loaded is not None
    assert loaded.summary == "ok"

    assert await is_cooldown_active(10, AdviceTopic.PRICING_STRATEGY) is False
    await set_brief_cooldown(10, AdviceTopic.PRICING_STRATEGY)
    assert await is_cooldown_active(10, AdviceTopic.PRICING_STRATEGY) is True


@pytest.mark.asyncio
async def test_run_tool_set_sequential_collects_warnings() -> None:
    async def _runner(tool: str, payload: dict) -> ToolResponse:
        del payload
        if tool == "kpi_compare":
            return ToolResponse.ok(
                correlation_id="c1",
                data={
                    "totals_a": {"revenue_net_sum": 1200, "orders_paid_sum": 14},
                    "totals_b": {"revenue_net_sum": 1000, "orders_paid_sum": 11},
                    "aov_a": 85,
                    "aov_b": 90,
                    "delta": {"revenue_net_sum": {"delta_pct": 20.0}},
                },
                provenance=ToolProvenance(window={"days": 7}),
            )
        return ToolResponse(
            status="error",
            correlation_id="c2",
            as_of=ToolResponse.ok(correlation_id="x", data={}, provenance=ToolProvenance()).as_of,
            error=ToolError(code="UPSTREAM_NOT_IMPLEMENTED", message="x"),
            provenance=ToolProvenance(),
        )

    result = await run_tool_set_sequential(
        topic=AdviceTopic.PROMO_STRATEGY,
        tool_runner=_runner,
        calls=[ToolCallSpec("kpi_compare", {}), ToolCallSpec("revenue_trend", {})],
    )
    assert result.tools_run[0]["ok"] is True
    assert result.tools_run[1]["ok"] is False
    assert result.warnings
    assert "kpi" in result.facts
