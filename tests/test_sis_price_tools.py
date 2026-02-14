from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.impl.sis_fx_reprice import Payload as RepricePayload, handle as reprice_handle
from app.tools.impl.sis_fx_rollback import Payload as RollbackPayload, handle as rollback_handle
from app.tools.impl.sis_prices_bump import Payload as BumpPayload, handle as bump_handle


@pytest.mark.asyncio
async def test_bump_preview_ok(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.sis_prices_bump.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))

    async def _run(**kwargs):
        return ToolResponse.ok(correlation_id="c", data={"affected_count": 10}, provenance=ToolProvenance(sources=["sis"]))

    monkeypatch.setattr("app.tools.impl.sis_prices_bump.run_sis_action", _run)
    resp = await bump_handle(BumpPayload(bump_percent="10", dry_run=True), "corr-1", session=None, actor=ToolActor(owner_user_id=1))
    assert resp.status == "ok"


@pytest.mark.asyncio
async def test_bump_apply_ok(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.sis_prices_bump.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))

    async def _run(**kwargs):
        return ToolResponse.ok(correlation_id="c", data={"summary": "ok"}, provenance=ToolProvenance(sources=["sis"]))

    monkeypatch.setattr("app.tools.impl.sis_prices_bump.run_sis_action", _run)
    resp = await bump_handle(BumpPayload(bump_percent="10", dry_run=False), "corr-2", session=None, actor=ToolActor(owner_user_id=1))
    assert resp.status == "ok"


@pytest.mark.asyncio
async def test_reprice_preview_and_apply_conflict_and_force_ok(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.sis_fx_reprice.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))

    async def _run_preview(**kwargs):
        return ToolResponse.ok(
            correlation_id="c",
            data={"anomaly": {"over_threshold_count": 2}, "warnings": ["force required for apply"]},
            provenance=ToolProvenance(sources=["sis"]),
        )

    monkeypatch.setattr("app.tools.impl.sis_fx_reprice.run_sis_action", _run_preview)
    preview = await reprice_handle(
        RepricePayload(rate_set_id="h", input_currency="USD", shop_currency="EUR", dry_run=True),
        "corr-3",
        session=None,
        actor=ToolActor(owner_user_id=1),
    )
    assert preview.status == "ok"

    async def _run_conflict(**kwargs):
        return ToolResponse.fail(
            correlation_id="c",
            code="ACTION_CONFLICT",
            message="Нужно явное подтверждение: применить несмотря на аномалию",
        )

    monkeypatch.setattr("app.tools.impl.sis_fx_reprice.run_sis_action", _run_conflict)
    apply_no_force = await reprice_handle(
        RepricePayload(rate_set_id="h", input_currency="USD", shop_currency="EUR", dry_run=False, force=False),
        "corr-4",
        session=None,
        actor=ToolActor(owner_user_id=1),
    )
    assert apply_no_force.status == "error"

    async def _run_ok(**kwargs):
        return ToolResponse.ok(correlation_id="c", data={"summary": "done"}, provenance=ToolProvenance(sources=["sis"]))

    monkeypatch.setattr("app.tools.impl.sis_fx_reprice.run_sis_action", _run_ok)
    apply_force = await reprice_handle(
        RepricePayload(rate_set_id="h", input_currency="USD", shop_currency="EUR", dry_run=False, force=True),
        "corr-5",
        session=None,
        actor=ToolActor(owner_user_id=1),
    )
    assert apply_force.status == "ok"


@pytest.mark.asyncio
async def test_rollback_apply_409(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.sis_fx_rollback.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))

    async def _run(**kwargs):
        return ToolResponse.fail(correlation_id="c", code="ACTION_CONFLICT", message="Нет данных для отката")

    monkeypatch.setattr("app.tools.impl.sis_fx_rollback.run_sis_action", _run)
    resp = await rollback_handle(RollbackPayload(dry_run=False), "corr-6", session=None, actor=ToolActor(owner_user_id=1))
    assert resp.status == "error"
    assert resp.error.code == "ACTION_CONFLICT"
