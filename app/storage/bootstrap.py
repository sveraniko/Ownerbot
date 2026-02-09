from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.db import session_scope
from app.core.logging import get_correlation_id
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
        orders: Sequence[OwnerbotDemoOrder] = [
            OwnerbotDemoOrder(
                order_id=order_id,
                status=status,
                amount=amount,
                currency="EUR",
                customer_id=f"cust_{index + 1:03d}",
            )
            for index, (order_id, status, amount) in enumerate(
                [
                    ("OB-1001", "pending", 120.00),
                    ("OB-1002", "paid", 89.50),
                    ("OB-1003", "stuck", 199.99),
                    ("OB-1004", "paid", 45.00),
                    ("OB-1005", "stuck", 310.10),
                    ("OB-1006", "pending", 150.75),
                    ("OB-1007", "paid", 59.99),
                    ("OB-1008", "stuck", 220.40),
                    ("OB-1009", "paid", 95.25),
                    ("OB-1010", "paid", 180.00),
                ]
            )
            if order_id not in existing_order_ids
        ]

        existing_threads = await session.execute(select(OwnerbotDemoChatThread.thread_id))
        existing_thread_ids = {row[0] for row in existing_threads.all()}
        now = utcnow()
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


async def write_audit_event(event_type: str, payload: dict) -> None:
    from app.storage.models import OwnerbotAuditEvent

    async with session_scope() as session:
        event = OwnerbotAuditEvent(
            correlation_id=get_correlation_id(),
            event_type=event_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        session.add(event)
        await session.commit()
