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
from app.storage.models import OwnerbotDemoKpiDaily, OwnerbotDemoOrder


def _alembic_config() -> Config:
    config_path = Path(__file__).parent / "alembic.ini"
    config = Config(str(config_path))
    return config


def run_migrations() -> None:
    command.upgrade(_alembic_config(), "head")


async def seed_demo_data() -> None:
    async with session_scope() as session:
        result = await session.execute(select(OwnerbotDemoKpiDaily).limit(1))
        if result.scalar_one_or_none() is not None:
            return
        today = date.today()
        rows = [
            OwnerbotDemoKpiDaily(
                day=today - timedelta(days=1),
                revenue_gross=1250.50,
                revenue_net=1100.20,
                orders_paid=14,
                orders_created=20,
                aov=89.32,
            ),
            OwnerbotDemoKpiDaily(
                day=today,
                revenue_gross=980.10,
                revenue_net=870.45,
                orders_paid=9,
                orders_created=12,
                aov=81.68,
            ),
        ]
        orders: Sequence[OwnerbotDemoOrder] = [
            OwnerbotDemoOrder(
                order_id="OB-1001",
                status="pending",
                amount=120.00,
                currency="EUR",
                customer_id="cust_001",
            ),
            OwnerbotDemoOrder(
                order_id="OB-1002",
                status="paid",
                amount=89.50,
                currency="EUR",
                customer_id="cust_002",
            ),
            OwnerbotDemoOrder(
                order_id="OB-1003",
                status="stuck",
                amount=199.99,
                currency="EUR",
                customer_id="cust_003",
            ),
        ]
        session.add_all(rows)
        session.add_all(orders)
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
