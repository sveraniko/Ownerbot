from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.impl.sis_discounts_clear import Payload as DiscountsClearPayload, handle as discounts_clear_handle
from app.tools.impl.sis_discounts_set import Payload as DiscountsSetPayload, handle as discounts_set_handle
from app.tools.impl.sis_looks_publish import Payload as LooksPublishPayload, handle as looks_publish_handle
from app.tools.impl.sis_products_publish import Payload as ProductsPublishPayload, handle as products_publish_handle


@pytest.mark.asyncio
async def test_products_publish_preview_and_apply_endpoints(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.sis_products_publish.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))
    seen = []

    async def _run(**kwargs):
        seen.append((kwargs["path"], kwargs["payload"]))
        return ToolResponse.ok(correlation_id="c", data={}, provenance=ToolProvenance(sources=["sis"]))

    monkeypatch.setattr("app.tools.impl.sis_products_publish.run_sis_action", _run)
    await products_publish_handle(ProductsPublishPayload(product_ids=["1"], target_status="ACTIVE", dry_run=True), "c", None, ToolActor(owner_user_id=7))
    await products_publish_handle(ProductsPublishPayload(status_from="ACTIVE", target_status="ARCHIVED", dry_run=False, force=True), "c", None, ToolActor(owner_user_id=7))
    assert seen[0][0] == "/products/publish/preview"
    assert "force" not in seen[0][1]
    assert seen[1][0] == "/products/publish/apply"
    assert seen[1][1]["force"] is True


@pytest.mark.asyncio
async def test_looks_publish_preview_and_apply_endpoints(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.sis_looks_publish.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))
    seen = []

    async def _run(**kwargs):
        seen.append((kwargs["path"], kwargs["payload"]))
        return ToolResponse.ok(correlation_id="c", data={}, provenance=ToolProvenance(sources=["sis"]))

    monkeypatch.setattr("app.tools.impl.sis_looks_publish.run_sis_action", _run)
    await looks_publish_handle(LooksPublishPayload(look_ids=["lk1"], target_active=True, dry_run=True), "c", None, ToolActor(owner_user_id=7))
    await looks_publish_handle(LooksPublishPayload(is_active_from=True, target_active=False, dry_run=False, force=True), "c", None, ToolActor(owner_user_id=7))
    assert seen[0][0] == "/looks/publish/preview"
    assert "force" not in seen[0][1]
    assert seen[1][0] == "/looks/publish/apply"
    assert seen[1][1]["force"] is True


@pytest.mark.asyncio
async def test_discounts_tools_preview_and_apply_endpoints(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.sis_discounts_clear.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))
    monkeypatch.setattr("app.tools.impl.sis_discounts_set.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))
    seen = []

    async def _run_clear(**kwargs):
        seen.append(("clear", kwargs["path"], kwargs["payload"]))
        return ToolResponse.ok(correlation_id="c", data={}, provenance=ToolProvenance(sources=["sis"]))

    async def _run_set(**kwargs):
        seen.append(("set", kwargs["path"], kwargs["payload"]))
        return ToolResponse.ok(correlation_id="c", data={}, provenance=ToolProvenance(sources=["sis"]))

    monkeypatch.setattr("app.tools.impl.sis_discounts_clear.run_sis_action", _run_clear)
    monkeypatch.setattr("app.tools.impl.sis_discounts_set.run_sis_action", _run_set)

    await discounts_clear_handle(DiscountsClearPayload(product_ids=["1"], dry_run=True), "c", None, ToolActor(owner_user_id=3))
    await discounts_clear_handle(DiscountsClearPayload(dry_run=False, force=True), "c", None, ToolActor(owner_user_id=3))
    await discounts_set_handle(DiscountsSetPayload(product_ids=["1"], discount_percent=25, dry_run=True), "c", None, ToolActor(owner_user_id=3))
    await discounts_set_handle(DiscountsSetPayload(stock_lte=5, discount_percent=30, dry_run=False, force=True), "c", None, ToolActor(owner_user_id=3))

    assert seen[0][1] == "/discounts/clear/preview"
    assert "force" not in seen[0][2]
    assert seen[1][1] == "/discounts/clear/apply"
    assert seen[1][2]["force"] is True
    assert seen[2][1] == "/discounts/set/preview"
    assert "force" not in seen[2][2]
    assert seen[3][1] == "/discounts/set/apply"
    assert seen[3][2]["force"] is True
