from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.diagnostics.systems import DiagnosticsContext, format_shadow_report, run_shadow_check
from app.tools.contracts import ToolProvenance, ToolResponse


@pytest.mark.asyncio
async def test_shadow_check_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _audit(*args, **kwargs):
        return None

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(correlation_id="c1", data={"totals": {"revenue": 10.0}}, provenance=ToolProvenance())

    async def _run_sis_tool(**kwargs):
        return ToolResponse.ok(correlation_id="c1", data={"totals": {"revenue": 10.001}}, provenance=ToolProvenance())

    monkeypatch.setattr("app.diagnostics.systems._safe_audit", _audit)
    monkeypatch.setattr("app.diagnostics.systems.run_tool", _run_tool)
    monkeypatch.setattr("app.diagnostics.systems.run_sis_tool", _run_sis_tool)

    settings = SimpleNamespace(sis_base_url="https://sis.local")
    report = await run_shadow_check(
        DiagnosticsContext(settings=settings, redis=None, correlation_id="c1", sis_client=None),
        presets=["kpi_snapshot_7"],
    )

    assert report.results[0].status == "OK"


@pytest.mark.asyncio
async def test_shadow_check_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _audit(event_type: str, payload: dict, *, correlation_id: str):
        calls.append(event_type)

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(correlation_id="c1", data={"pending_orders": 2}, provenance=ToolProvenance())

    async def _run_sis_tool(**kwargs):
        return ToolResponse.ok(correlation_id="c1", data={"pending_orders": 5}, provenance=ToolProvenance())

    monkeypatch.setattr("app.diagnostics.systems._safe_audit", _audit)
    monkeypatch.setattr("app.diagnostics.systems.run_tool", _run_tool)
    monkeypatch.setattr("app.diagnostics.systems.run_sis_tool", _run_sis_tool)

    settings = SimpleNamespace(sis_base_url="https://sis.local")
    report = await run_shadow_check(
        DiagnosticsContext(settings=settings, redis=None, correlation_id="c1", sis_client=None),
        presets=["orders_search_stuck"],
    )

    assert report.results[0].status == "MISMATCH"
    assert report.results[0].diff[0].key == "pending_orders"
    assert "shadow_mismatch" in calls
    text = format_shadow_report(report)
    assert "demo=2.0" in text


@pytest.mark.asyncio
async def test_shadow_check_unavailable_when_sis_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _audit(*args, **kwargs):
        return None

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(correlation_id="c1", data={"ok": True}, provenance=ToolProvenance())

    monkeypatch.setattr("app.diagnostics.systems._safe_audit", _audit)
    monkeypatch.setattr("app.diagnostics.systems.run_tool", _run_tool)

    settings = SimpleNamespace(sis_base_url="")
    report = await run_shadow_check(
        DiagnosticsContext(settings=settings, redis=None, correlation_id="c1", sis_client=None),
        presets=["revenue_trend_7"],
    )

    assert report.results[0].status == "UNAVAILABLE"
    assert report.results[0].error_code == "SIS_NOT_CONFIGURED"
