from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Base, OwnerbotDemoOrder, OwnerbotDemoOrderItem, OwnerbotDemoProduct
from app.tools.impl._forecasting import confidence_from, forecast_ses, forecast_sma
from app.tools.impl.demand_forecast import Payload as DemandPayload, handle as demand_handle
from app.tools.impl.reorder_plan import Payload as ReorderPayload, handle as reorder_handle


@pytest.mark.parametrize(
    ("series", "window", "expected"),
    [([4.0, 0.0, 2.0, 0.0], 3, 0.67), ([0.0, 0.0, 0.0], 5, 0.0)],
)
def test_forecast_sma_includes_zeros(series: list[float], window: int, expected: float) -> None:
    assert round(forecast_sma(series, window), 2) == expected


@pytest.mark.parametrize("alpha", [0.05, 0.95])
def test_forecast_ses_alpha_boundaries(alpha: float) -> None:
    value = forecast_ses([2.0, 0.0, 4.0, 1.0], alpha)
    assert value >= 0.0


def test_confidence_grading() -> None:
    assert confidence_from([1.0] * 10 + [0.0] * 20, history_days=30) == "HIGH"
    assert confidence_from([1.0] * 5 + [0.0] * 9, history_days=14) == "MED"
    assert confidence_from([1.0] * 2 + [0.0] * 8, history_days=10) == "LOW"


@pytest.mark.asyncio
async def test_reorder_plan_formula_and_sorting(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.reorder_plan.get_settings", lambda: SimpleNamespace(upstream_mode="DEMO"))
    monkeypatch.setattr("app.tools.impl.demand_forecast.get_settings", lambda: SimpleNamespace(upstream_mode="DEMO"))

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotDemoProduct(product_id="PRD-A", title="A", category="Тайтсы", price=30.0, currency="EUR", stock_qty=5),
                OwnerbotDemoProduct(product_id="PRD-B", title="B", category="Тайтсы", price=25.0, currency="EUR", stock_qty=50),
            ]
        )
        session.add_all(
            [
                OwnerbotDemoOrder(order_id="OB-X1", status="paid", amount=90, currency="EUR", customer_id="c1", payment_status="paid"),
                OwnerbotDemoOrder(order_id="OB-X2", status="paid", amount=90, currency="EUR", customer_id="c2", payment_status="paid"),
            ]
        )
        session.add_all(
            [
                OwnerbotDemoOrderItem(order_id="OB-X1", product_id="PRD-A", qty=3, unit_price=30, currency="EUR"),
                OwnerbotDemoOrderItem(order_id="OB-X2", product_id="PRD-A", qty=3, unit_price=30, currency="EUR"),
            ]
        )
        await session.commit()

    async with async_session() as session:
        demand = await demand_handle(DemandPayload(history_days=30, horizon_days=7), "corr", session)
        reorder = await reorder_handle(
            ReorderPayload(history_days=30, horizon_days=14, lead_time_days=14, safety_stock_days=7, limit=10),
            "corr",
            session,
        )

    assert demand.status == "ok"
    assert reorder.status == "ok"
    assert reorder.data["items"]
    first = reorder.data["items"][0]
    assert first["product_id"] == "PRD-A"
    assert first["reorder_needed"] is True
    assert first["recommended_order_qty"] >= 0
    assert first["reorder_point"] >= 0


@pytest.mark.asyncio
async def test_forecast_tools_non_demo(monkeypatch) -> None:
    monkeypatch.setattr("app.tools.impl.reorder_plan.get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP"))
    monkeypatch.setattr("app.tools.impl.demand_forecast.get_settings", lambda: SimpleNamespace(upstream_mode="AUTO"))

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        response_a = await demand_handle(DemandPayload(), "corr", session)
        response_b = await reorder_handle(ReorderPayload(), "corr", session)

    assert response_a.status == "error"
    assert response_b.status == "error"
    assert response_a.error and response_a.error.code == "UPSTREAM_NOT_IMPLEMENTED"
    assert response_b.error and response_b.error.code == "UPSTREAM_NOT_IMPLEMENTED"
