from datetime import date, datetime, timezone, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Base, OwnerbotDemoChatThread, OwnerbotDemoKpiDaily, OwnerbotDemoOrder
from app.tools.impl.chats_unanswered import Payload as ChatsPayload, handle as chats_handle
from app.tools.impl.order_detail import Payload as OrderPayload, handle as order_handle
from app.tools.impl.revenue_trend import Payload as TrendPayload, handle as trend_handle


@pytest.mark.asyncio
async def test_revenue_trend_demo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    start_day = date(2024, 1, 1)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        for offset in range(14):
            day = start_day + timedelta(days=offset)
            session.add(
                OwnerbotDemoKpiDaily(
                    day=day,
                    revenue_gross=100.0 + offset,
                    revenue_net=90.0 + offset,
                    orders_paid=5 + offset,
                    orders_created=6 + offset,
                    aov=20.0 + offset,
                )
            )
        await session.commit()

    async with async_session() as session:
        payload = TrendPayload(days=7, end_day=date(2024, 1, 14))
        response = await trend_handle(payload, "corr", session)

    assert response.status == "ok"
    assert len(response.data["series"]) == 7
    assert response.data["totals"]["revenue_gross"] > 0
    assert response.provenance.sources


@pytest.mark.asyncio
async def test_order_detail_demo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add(
            OwnerbotDemoOrder(
                order_id="OB-9999",
                status="paid",
                amount=123.45,
                currency="EUR",
                customer_id="cust_999",
            )
        )
        await session.commit()

    async with async_session() as session:
        payload = OrderPayload(order_id="OB-9999")
        response = await order_handle(payload, "corr", session)

    assert response.status == "ok"
    assert response.data["order_id"] == "OB-9999"


@pytest.mark.asyncio
async def test_chats_unanswered_demo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    async with async_session() as session:
        session.add(
            OwnerbotDemoChatThread(
                thread_id="TH-1",
                customer_id="cust_1",
                open=True,
                last_customer_message_at=now - timedelta(hours=1),
                last_manager_reply_at=None,
            )
        )
        session.add(
            OwnerbotDemoChatThread(
                thread_id="TH-2",
                customer_id="cust_2",
                open=True,
                last_customer_message_at=now - timedelta(hours=2),
                last_manager_reply_at=now,
            )
        )
        await session.commit()

    async with async_session() as session:
        payload = ChatsPayload(limit=10)
        response = await chats_handle(payload, "corr", session)

    assert response.status == "ok"
    assert response.data["count"] == 1
