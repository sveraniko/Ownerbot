from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.audit import write_audit_event
from app.core.db import session_scope
from app.core.time import utcnow
from app.storage.models import OwnerbotDemoKpiDaily, OwnerbotDemoOrder, OwnerbotDemoChatThread


def _alembic_config() -> Config:
    config_path = Path(__file__).parent / "alembic.ini"
    config = Config(str(config_path))
    return config


def run_migrations() -> None:
    command.upgrade(_alembic_config(), "head")


async def seed_demo_data() -> None:
    async with session_scope() as session:
        today = date.today()
        kpi_days = [today - timedelta(days=offset) for offset in range(13, -1, -1)]
        existing_kpi = await session.execute(select(OwnerbotDemoKpiDaily.day))
        existing_kpi_days = {row[0] for row in existing_kpi.all()}
        kpi_rows = [
            OwnerbotDemoKpiDaily(
                day=day,
                revenue_gross=900.0 + idx * 35.5,
                revenue_net=820.0 + idx * 30.2,
                orders_paid=8 + idx % 7,
                orders_created=12 + idx % 6,
                aov=75.0 + idx * 2.1,
            )
            for idx, day in enumerate(kpi_days)
            if day not in existing_kpi_days
        ]

        existing_orders = await session.execute(select(OwnerbotDemoOrder.order_id))
        existing_order_ids = {row[0] for row in existing_orders.all()}
        now = utcnow()
        demo_orders = [
            {
                "order_id": "OB-1001",
                "status": "pending",
                "amount": 120.00,
                "customer_phone": "+491700000001",
                "payment_status": "pending",
                "shipping_status": "pending",
                "created_at": now - timedelta(hours=8),
                "ship_due_at": now - timedelta(hours=2),
            },
            {
                "order_id": "OB-1002",
                "status": "paid",
                "amount": 89.50,
                "customer_phone": "+491700000002",
                "payment_status": "paid",
                "paid_at": now - timedelta(hours=10),
                "shipping_status": "pending",
                "created_at": now - timedelta(hours=12),
                "ship_due_at": now - timedelta(hours=3),
            },
            {
                "order_id": "OB-1003",
                "status": "stuck",
                "amount": 199.99,
                "payment_status": "failed",
                "shipping_status": "pending",
                "created_at": now - timedelta(hours=5),
                "flagged": False,
                "flag_reason": None,
            },
            {
                "order_id": "OB-1004",
                "status": "paid",
                "amount": 45.00,
                "customer_phone": "+491700000004",
                "payment_status": "paid",
                "paid_at": now - timedelta(hours=6),
                "shipping_status": "shipped",
                "ship_due_at": now - timedelta(hours=5),
                "shipped_at": now - timedelta(hours=4),
            },
            {
                "order_id": "OB-1005",
                "status": "stuck",
                "amount": 310.10,
                "payment_status": "pending",
                "shipping_status": "pending",
                "created_at": now - timedelta(hours=9),
            },
            {
                "order_id": "OB-1006",
                "status": "pending",
                "amount": 150.75,
                "payment_status": "pending",
                "shipping_status": "pending",
                "created_at": now - timedelta(hours=1),
            },
            {
                "order_id": "OB-1007",
                "status": "paid",
                "amount": 59.99,
                "payment_status": "paid",
                "paid_at": now - timedelta(hours=16),
                "shipping_status": "pending",
                "created_at": now - timedelta(hours=20),
                "ship_due_at": now - timedelta(hours=8),
            },
            {
                "order_id": "OB-1008",
                "status": "stuck",
                "amount": 220.40,
                "payment_status": "failed",
                "shipping_status": "pending",
                "created_at": now - timedelta(hours=7),
            },
            {
                "order_id": "OB-1009",
                "status": "paid",
                "amount": 95.25,
                "customer_phone": "+491700000009",
                "payment_status": "paid",
                "paid_at": now - timedelta(hours=3),
                "shipping_status": "pending",
                "ship_due_at": now + timedelta(hours=4),
            },
            {
                "order_id": "OB-1010",
                "status": "paid",
                "amount": 180.00,
                "payment_status": "refunded",
                "shipping_status": "pending",
                "created_at": now - timedelta(hours=11),
            },
        ]
        orders: Sequence[OwnerbotDemoOrder] = [
            OwnerbotDemoOrder(
                order_id=order_data["order_id"],
                status=order_data["status"],
                amount=order_data["amount"],
                currency="EUR",
                customer_id=f"cust_{index + 1:03d}",
                customer_phone=order_data.get("customer_phone"),
                payment_status=order_data.get("payment_status"),
                paid_at=order_data.get("paid_at"),
                shipping_status=order_data.get("shipping_status"),
                ship_due_at=order_data.get("ship_due_at"),
                shipped_at=order_data.get("shipped_at"),
                created_at=order_data.get("created_at", now),
                flagged=order_data.get("flagged", False),
                flag_reason=order_data.get("flag_reason"),
            )
            for index, order_data in enumerate(demo_orders)
            if order_data["order_id"] not in existing_order_ids
        ]

        existing_threads = await session.execute(select(OwnerbotDemoChatThread.thread_id))
        existing_thread_ids = {row[0] for row in existing_threads.all()}
        threads = [
            OwnerbotDemoChatThread(
                thread_id="TH-2001",
                customer_id="cust_001",
                open=True,
                last_customer_message_at=now - timedelta(hours=2),
                last_manager_reply_at=None,
            ),
            OwnerbotDemoChatThread(
                thread_id="TH-2002",
                customer_id="cust_002",
                open=True,
                last_customer_message_at=now - timedelta(hours=5),
                last_manager_reply_at=now - timedelta(hours=6),
            ),
            OwnerbotDemoChatThread(
                thread_id="TH-2003",
                customer_id="cust_003",
                open=True,
                last_customer_message_at=now - timedelta(hours=12),
                last_manager_reply_at=None,
            ),
            OwnerbotDemoChatThread(
                thread_id="TH-2004",
                customer_id="cust_004",
                open=False,
                last_customer_message_at=now - timedelta(days=1),
                last_manager_reply_at=now - timedelta(days=1, hours=1),
            ),
            OwnerbotDemoChatThread(
                thread_id="TH-2005",
                customer_id="cust_005",
                open=True,
                last_customer_message_at=now - timedelta(hours=9),
                last_manager_reply_at=None,
            ),
            OwnerbotDemoChatThread(
                thread_id="TH-2006",
                customer_id="cust_006",
                open=True,
                last_customer_message_at=now - timedelta(hours=3),
                last_manager_reply_at=now - timedelta(hours=1),
            ),
        ]
        threads = [thread for thread in threads if thread.thread_id not in existing_thread_ids]

        session.add_all(kpi_rows)
        session.add_all(orders)
        session.add_all(threads)
        await session.commit()
