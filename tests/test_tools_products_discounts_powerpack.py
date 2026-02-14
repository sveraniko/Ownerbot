from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Base, OwnerbotDemoCoupon, OwnerbotDemoProduct
from app.tools.impl.adjust_price import Payload as AdjustPayload, handle as adjust_handle
from app.tools.impl.coupons_status import Payload as CouponStatusPayload, handle as coupon_status_handle
from app.tools.impl.coupons_top_used import Payload as CouponTopPayload, handle as coupon_top_handle
from app.tools.impl.create_coupon import Payload as CreateCouponPayload, handle as create_coupon_handle
from app.tools.impl.inventory_status import Payload as InventoryPayload, handle as inventory_handle


@pytest.mark.asyncio
async def test_inventory_status_section_filters_extended() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotDemoProduct(product_id="P1", title="NoVideo", category="C", price=10, currency="EUR", stock_qty=5, has_photo=True, has_video=False, return_flagged=False, published=True),
                OwnerbotDemoProduct(product_id="P2", title="Return", category="C", price=10, currency="EUR", stock_qty=5, has_photo=True, has_video=True, return_flagged=True, published=True),
            ]
        )
        await session.commit()

    async with async_session() as session:
        response = await inventory_handle(InventoryPayload(section="missing_video", limit=20), "corr", session)
    assert response.status == "ok"
    assert response.data["header"]["section"] == "missing_video"
    assert {item["product_id"] for item in response.data["missing_video"]} == {"P1"}


@pytest.mark.asyncio
async def test_adjust_price_preview_no_change_and_commit(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.adjust_price.get_settings", lambda: SimpleNamespace(upstream_mode="DEMO"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add(OwnerbotDemoProduct(product_id="P1", title="Prod", category="C", price=10, currency="EUR", stock_qty=3, has_photo=True, published=True))
        await session.commit()

    async with async_session() as session:
        preview = await adjust_handle(AdjustPayload(dry_run=True, product_ids=["P1"], mode="set", value=10, rounding="none"), "c1", session)
    assert preview.status == "ok"
    assert preview.data["status"] == "no_change"

    async with async_session() as session:
        commit = await adjust_handle(AdjustPayload(dry_run=False, product_ids=["P1"], mode="delta_percent", value=20, rounding="none"), "c2", session)
    assert commit.status == "ok"
    assert commit.data["affected_count"] == 1


@pytest.mark.asyncio
async def test_adjust_price_guardrail_requires_force(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.adjust_price.get_settings", lambda: SimpleNamespace(upstream_mode="DEMO"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add(OwnerbotDemoProduct(product_id="P1", title="Prod", category="C", price=10, currency="EUR", stock_qty=3, has_photo=True, published=True))
        await session.commit()

    async with async_session() as session:
        response = await adjust_handle(AdjustPayload(dry_run=True, product_ids=["P1"], mode="delta_percent", value=31, rounding="none"), "c3", session)
    assert response.status == "error"
    assert response.error and response.error.code == "FORCE_REQUIRED"


@pytest.mark.asyncio
async def test_create_coupon_and_reports(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.create_coupon.get_settings", lambda: SimpleNamespace(upstream_mode="DEMO"))
    monkeypatch.setattr("app.tools.impl.coupons_status.get_settings", lambda: SimpleNamespace(upstream_mode="DEMO"))
    monkeypatch.setattr("app.tools.impl.coupons_top_used.get_settings", lambda: SimpleNamespace(upstream_mode="DEMO"))

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add(OwnerbotDemoCoupon(code="WELCOME10", percent_off=10, amount_off=None, active=True, max_uses=100, used_count=5))
        await session.commit()

    async with async_session() as session:
        dry = await create_coupon_handle(CreateCouponPayload(dry_run=True, code="welcome10", percent_off=15, max_uses=200), "c4", session)
    assert dry.status == "ok"
    assert dry.data["operation"] == "update"

    async with async_session() as session:
        commit = await create_coupon_handle(CreateCouponPayload(dry_run=False, code="new20", percent_off=20, max_uses=100), "c5", session)
    assert commit.status == "ok"
    assert commit.data["operation"] == "create"

    async with async_session() as session:
        status_resp = await coupon_status_handle(CouponStatusPayload(), "c6", session)
        top_resp = await coupon_top_handle(CouponTopPayload(limit=3), "c7", session)

    assert status_resp.status == "ok"
    assert status_resp.data["total_active"] >= 1
    assert top_resp.status == "ok"
    assert len(top_resp.data["rows"]) >= 1
