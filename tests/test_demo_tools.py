from datetime import date, datetime, timezone, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import (
    Base,
    OwnerbotDemoChatThread,
    OwnerbotDemoKpiDaily,
    OwnerbotDemoOrder,
    OwnerbotDemoOrderItem,
    OwnerbotDemoProduct,
)
from app.tools.contracts import ToolActor
from app.tools.impl.bulk_flag_order import Payload as BulkFlagPayload, handle as bulk_flag_handle
from app.tools.impl.chats_unanswered import Payload as ChatsPayload, handle as chats_handle
from app.tools.impl.inventory_status import Payload as InventoryPayload, handle as inventory_handle
from app.tools.impl.kpi_compare import Payload as ComparePayload, handle as compare_handle
from app.tools.impl.order_detail import Payload as OrderPayload, handle as order_handle
from app.tools.impl.orders_search import OrdersSearchPayload, handle as orders_search_handle
from app.tools.impl.revenue_trend import Payload as TrendPayload, handle as trend_handle
from app.tools.impl.team_queue_summary import Payload as TeamQueuePayload, handle as team_queue_handle
from app.tools.impl.top_products import Payload as TopProductsPayload, handle as top_products_handle


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
                customer_phone="+491700999999",
                payment_status="paid",
                paid_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
                shipping_status="pending",
                ship_due_at=datetime(2024, 1, 11, tzinfo=timezone.utc),
            )
        )
        await session.commit()

    async with async_session() as session:
        payload = OrderPayload(order_id="OB-9999")
        response = await order_handle(payload, "corr", session)

    assert response.status == "ok"
    assert response.data["order_id"] == "OB-9999"
    assert response.data["customer_phone"] == "+491700999999"
    assert response.data["payment_status"] == "paid"


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


async def _seed_orders(async_session):
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotDemoOrder(
                    order_id="OB-LATE-1",
                    status="paid",
                    amount=100,
                    currency="EUR",
                    customer_id="cust_late_1",
                    payment_status="paid",
                    shipping_status="pending",
                    ship_due_at=now - timedelta(hours=1),
                    created_at=now - timedelta(hours=10),
                    customer_phone="+491700111111",
                    flagged=False,
                ),
                OwnerbotDemoOrder(
                    order_id="OB-LATE-2",
                    status="paid",
                    amount=120,
                    currency="EUR",
                    customer_id="cust_late_2",
                    payment_status="paid",
                    shipping_status="pending",
                    ship_due_at=now - timedelta(hours=2),
                    created_at=now - timedelta(hours=12),
                    flagged=False,
                ),
                OwnerbotDemoOrder(
                    order_id="OB-FAILED-1",
                    status="pending",
                    amount=80,
                    currency="EUR",
                    customer_id="cust_fail_1",
                    payment_status="failed",
                    created_at=now - timedelta(hours=4),
                    flagged=False,
                ),
                OwnerbotDemoOrder(
                    order_id="OB-PENDING-OLD",
                    status="pending",
                    amount=90,
                    currency="EUR",
                    customer_id="cust_pending_old",
                    payment_status="pending",
                    created_at=now - timedelta(hours=5),
                    flagged=False,
                ),
                OwnerbotDemoOrder(
                    order_id="OB-OK-1",
                    status="paid",
                    amount=70,
                    currency="EUR",
                    customer_id="cust_ok_1",
                    payment_status="paid",
                    shipping_status="shipped",
                    shipped_at=now - timedelta(hours=1),
                    created_at=now - timedelta(hours=3),
                    flagged=False,
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_orders_search_find_by_phone():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_orders(async_session)

    async with async_session() as session:
        response = await orders_search_handle(OrdersSearchPayload(q="111111", limit=20), "corr", session)

    assert response.status == "ok"
    assert response.data["count"] == 1
    assert response.data["items"][0]["order_id"] == "OB-LATE-1"


@pytest.mark.asyncio
async def test_orders_search_preset_late_ship():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_orders(async_session)

    async with async_session() as session:
        response = await orders_search_handle(OrdersSearchPayload(preset="late_ship", limit=20), "corr", session)

    assert response.status == "ok"
    ids = {item["order_id"] for item in response.data["items"]}
    assert ids == {"OB-LATE-1", "OB-LATE-2"}


@pytest.mark.asyncio
async def test_orders_search_preset_payment_issues():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_orders(async_session)

    async with async_session() as session:
        response = await orders_search_handle(OrdersSearchPayload(preset="payment_issues", limit=20), "corr", session)

    assert response.status == "ok"
    ids = {item["order_id"] for item in response.data["items"]}
    assert ids == {"OB-FAILED-1", "OB-PENDING-OLD"}


@pytest.mark.asyncio
async def test_bulk_flag_order_preview_commit_and_noop():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_orders(async_session)

    async with async_session() as session:
        preview = await bulk_flag_handle(
            BulkFlagPayload(preset="late_ship", reason="needs_attention", limit=20, dry_run=True),
            "corr",
            session,
        )
    assert preview.status == "ok"
    assert preview.data["status"] == "preview"
    assert preview.data["would_apply"] is True

    actor = ToolActor(owner_user_id=77)
    async with async_session() as session:
        commit = await bulk_flag_handle(
            BulkFlagPayload(preset="late_ship", reason="needs_attention", limit=20, dry_run=False),
            "corr",
            session,
            actor,
        )
    assert commit.status == "ok"
    assert commit.data["updated_count"] == 2

    async with async_session() as session:
        noop = await bulk_flag_handle(
            BulkFlagPayload(preset="late_ship", reason="needs_attention", limit=20, dry_run=True),
            "corr",
            session,
        )

    assert noop.status == "ok"
    assert noop.data["status"] == "noop"
    assert noop.data["would_apply"] is False


@pytest.mark.asyncio
async def test_kpi_compare_wow_and_custom():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    start_day = date.today() - timedelta(days=19)
    async with async_session() as session:
        for offset in range(20):
            day = start_day + timedelta(days=offset)
            session.add(
                OwnerbotDemoKpiDaily(
                    day=day,
                    revenue_gross=100 + offset * 3,
                    revenue_net=90 + offset * 2,
                    orders_paid=4 + (offset % 4),
                    orders_created=7 + (offset % 5),
                    aov=20 + offset,
                )
            )
        await session.commit()

    async with async_session() as session:
        wow = await compare_handle(ComparePayload(preset="wow", days=7), "corr", session)

    assert wow.status == "ok"
    assert set(wow.data["delta"].keys()) == {"revenue_gross_sum", "revenue_net_sum", "orders_paid_sum", "orders_created_sum"}
    assert "start" in wow.data["window_a"]

    async with async_session() as session:
        custom = await compare_handle(
            ComparePayload(
                preset="custom",
                a_start=start_day + timedelta(days=9),
                a_end=start_day + timedelta(days=11),
                b_start=start_day + timedelta(days=6),
                b_end=start_day + timedelta(days=8),
            ),
            "corr",
            session,
        )

    assert custom.status == "ok"
    assert custom.data["window_a"]["start"] == (start_day + timedelta(days=9)).isoformat()
    assert custom.data["window_b"]["end"] == (start_day + timedelta(days=8)).isoformat()


@pytest.mark.asyncio
async def test_team_queue_summary_buckets():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotDemoChatThread(thread_id="TH-A", customer_id="c1", open=True, last_customer_message_at=now - timedelta(hours=3), last_manager_reply_at=None),
                OwnerbotDemoChatThread(thread_id="TH-B", customer_id="c2", open=True, last_customer_message_at=now - timedelta(hours=8), last_manager_reply_at=None),
                OwnerbotDemoChatThread(thread_id="TH-C", customer_id="c3", open=True, last_customer_message_at=now - timedelta(hours=30), last_manager_reply_at=now - timedelta(hours=31)),
                OwnerbotDemoChatThread(thread_id="TH-D", customer_id="c4", open=True, last_customer_message_at=now - timedelta(hours=1), last_manager_reply_at=now),
            ]
        )
        await session.commit()

    async with async_session() as session:
        response = await team_queue_handle(TeamQueuePayload(), "corr", session)

    assert response.status == "ok"
    assert response.data["total_open_threads"] == 3
    assert response.data["unanswered_2h"] == 3
    assert response.data["unanswered_6h"] == 2
    assert response.data["unanswered_24h"] == 1


@pytest.mark.asyncio
async def test_top_products_revenue_ordering():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotDemoProduct(product_id="P1", title="Prod 1", category="CatA", price=10, currency="EUR", stock_qty=5, has_photo=True, published=True),
                OwnerbotDemoProduct(product_id="P2", title="Prod 2", category="CatA", price=30, currency="EUR", stock_qty=5, has_photo=True, published=True),
                OwnerbotDemoProduct(product_id="P3", title="Prod 3", category="CatB", price=25, currency="EUR", stock_qty=5, has_photo=True, published=True),
                OwnerbotDemoOrder(order_id="O1", status="paid", amount=70, currency="EUR", customer_id="c1", payment_status="paid", created_at=now - timedelta(days=1)),
                OwnerbotDemoOrder(order_id="O2", status="paid", amount=100, currency="EUR", customer_id="c2", payment_status="paid", created_at=now - timedelta(days=2)),
            ]
        )
        session.add_all(
            [
                OwnerbotDemoOrderItem(order_id="O1", product_id="P1", qty=1, unit_price=10, currency="EUR", created_at=now),
                OwnerbotDemoOrderItem(order_id="O1", product_id="P2", qty=2, unit_price=30, currency="EUR", created_at=now),
                OwnerbotDemoOrderItem(order_id="O2", product_id="P3", qty=4, unit_price=25, currency="EUR", created_at=now),
            ]
        )
        await session.commit()

    async with async_session() as session:
        response = await top_products_handle(TopProductsPayload(days=7, metric="revenue", direction="top", group_by="product", limit=10), "corr", session)

    assert response.status == "ok"
    assert response.data["rows"]
    assert response.data["rows"][0]["key"] == "P3"
    assert response.data["rows"][1]["key"] == "P2"


@pytest.mark.asyncio
async def test_inventory_status_categories():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotDemoProduct(product_id="P0", title="Out", category="C", price=10, currency="EUR", stock_qty=0, has_photo=True, published=True),
                OwnerbotDemoProduct(product_id="P1", title="Low", category="C", price=10, currency="EUR", stock_qty=3, has_photo=True, published=True),
                OwnerbotDemoProduct(product_id="P2", title="NoPhoto", category="C", price=10, currency="EUR", stock_qty=4, has_photo=False, published=True),
                OwnerbotDemoProduct(product_id="P3", title="NoPrice", category="C", price=0, currency="EUR", stock_qty=4, has_photo=True, published=True),
                OwnerbotDemoProduct(product_id="P4", title="Hidden", category="C", price=10, currency="EUR", stock_qty=0, has_photo=True, published=False),
            ]
        )
        await session.commit()

    async with async_session() as session:
        response = await inventory_handle(InventoryPayload(low_stock_lte=5, limit=20), "corr", session)

    assert response.status == "ok"
    assert response.data["counts"]["out_of_stock"] == 1
    assert response.data["counts"]["low_stock"] == 3
    assert {item["product_id"] for item in response.data["missing_photo"]} == {"P2"}
    assert {item["product_id"] for item in response.data["missing_price"]} == {"P3"}
    assert {item["product_id"] for item in response.data["unpublished"]} == {"P4"}
