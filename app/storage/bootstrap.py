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
from app.storage.models import (
    OwnerbotDemoChatThread,
    OwnerbotDemoKpiDaily,
    OwnerbotDemoOrder,
    OwnerbotDemoOrderItem,
    OwnerbotDemoProduct,
    OwnerbotDemoCoupon,
)


_PRODUCT_SEED = [
    ("PRD-001", "Тайтсы Core Black", "Тайтсы", 39.90, 20, True, True, True, False),
    ("PRD-002", "Тайтсы Motion Grey", "Тайтсы", 42.50, 5, True, True, True, False),
    ("PRD-003", "Тайтсы Zero Stock", "Тайтсы", 37.00, 0, True, True, True, False),
    ("PRD-004", "Тайтсы Draft", "Тайтсы", 41.00, 2, False, False, False, True),
    ("PRD-005", "Топ Breeze White", "Топы", 24.90, 20, True, True, True, False),
    ("PRD-006", "Топ Breeze Mint", "Топы", 0.0, 5, True, True, False, False),
    ("PRD-007", "Топ Active Noir", "Топы", 28.00, 2, False, True, True, True),
    ("PRD-008", "Топ Archive", "Топы", 21.00, 0, True, False, False, False),
    ("PRD-009", "Худи Urban Sand", "Худи", 59.90, 20, True, True, True, False),
    ("PRD-010", "Худи Urban Coal", "Худи", 62.00, 5, True, True, False, False),
    ("PRD-011", "Худи Lite", "Худи", 54.00, 2, False, True, True, True),
    ("PRD-012", "Худи Proto", "Худи", 0.0, 0, True, False, True, False),
    ("PRD-013", "Аксессуар Bottle", "Аксессуары", 14.90, 20, True, True, True, False),
    ("PRD-014", "Аксессуар Bag", "Аксессуары", 19.90, 5, True, True, False, False),
    ("PRD-015", "Аксессуар Belt", "Аксессуары", 17.00, 2, False, True, True, False),
    ("PRD-016", "Аксессуар Clip", "Аксессуары", 13.00, 0, True, True, True, True),
    ("PRD-017", "Куртка Storm", "Верхняя одежда", 89.00, 5, True, True, True, False),
    ("PRD-018", "Куртка Breeze", "Верхняя одежда", 0.0, 2, True, True, False, False),
    ("PRD-019", "Куртка Lab", "Верхняя одежда", 79.00, 0, False, False, True, True),
    ("PRD-020", "Куртка Urban", "Верхняя одежда", 85.00, 20, True, True, True, False),
    ("PRD-021", "Носки Core", "Базовые", 9.90, 20, True, True, True, False),
    ("PRD-022", "Носки Flex", "Базовые", 8.90, 5, True, True, True, False),
    ("PRD-023", "Носки Sample", "Базовые", 0.0, 2, False, True, False, True),
    ("PRD-024", "Носки Hidden", "Базовые", 7.50, 0, True, False, True, False),
]


def _build_order_items(now, paid_order_ids: list[str]) -> list[dict[str, object]]:
    product_ids = [row[0] for row in _PRODUCT_SEED]
    rows: list[dict[str, object]] = []
    for idx, order_id in enumerate(paid_order_ids):
        item_count = (idx % 4) + 1
        for item_offset in range(item_count):
            product_idx = (idx * 3 + item_offset * 5) % len(product_ids)
            product_id, _title, _category, price, _stock, _has_photo, _published, _has_video, _return_flagged = _PRODUCT_SEED[product_idx]
            qty = ((idx + item_offset) % 3) + 1
            unit_price = price if price > 0 else float(11 + idx + item_offset)
            rows.append(
                {
                    "order_id": order_id,
                    "product_id": product_id,
                    "qty": qty,
                    "unit_price": round(unit_price, 2),
                    "currency": "EUR",
                    "created_at": now - timedelta(hours=idx + item_offset),
                }
            )
    return rows


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
                "coupon_code": "WELCOME10",
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
                "coupon_code": "WELCOME10",
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
                coupon_code=order_data.get("coupon_code"),
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

        existing_products = await session.execute(select(OwnerbotDemoProduct.product_id))
        existing_product_ids = {row[0] for row in existing_products.all()}
        products = [
            OwnerbotDemoProduct(
                product_id=product_id,
                title=title,
                category=category,
                price=price,
                currency="EUR",
                stock_qty=stock_qty,
                has_photo=has_photo,
                has_video=has_video,
                return_flagged=return_flagged,
                published=published,
            )
            for product_id, title, category, price, stock_qty, has_photo, published, has_video, return_flagged in _PRODUCT_SEED
            if product_id not in existing_product_ids
        ]

        paid_order_ids = [
            order_data["order_id"]
            for order_data in demo_orders
            if order_data.get("status") == "paid" or order_data.get("payment_status") == "paid"
        ]
        existing_order_items = await session.execute(select(OwnerbotDemoOrderItem.order_id, OwnerbotDemoOrderItem.product_id))
        existing_item_keys = {(row[0], row[1]) for row in existing_order_items.all()}
        order_items = []
        for item in _build_order_items(now, paid_order_ids):
            item_key = (item["order_id"], item["product_id"])
            if item_key in existing_item_keys:
                continue
            existing_item_keys.add(item_key)
            order_items.append(
                OwnerbotDemoOrderItem(
                    order_id=item["order_id"],
                    product_id=item["product_id"],
                    qty=item["qty"],
                    unit_price=item["unit_price"],
                    currency=item["currency"],
                    created_at=item["created_at"],
                )
            )

        existing_coupons = await session.execute(select(OwnerbotDemoCoupon.code))
        existing_coupon_codes = {row[0] for row in existing_coupons.all()}
        coupon_seeds = [
            {"code": "WELCOME10", "percent_off": 10, "amount_off": None, "active": True, "max_uses": 200, "used_count": 34, "starts_at": now - timedelta(days=15), "ends_at": now + timedelta(days=45)},
            {"code": "VIP25", "percent_off": 25, "amount_off": None, "active": True, "max_uses": 80, "used_count": 22, "starts_at": now - timedelta(days=5), "ends_at": now + timedelta(days=20)},
            {"code": "SHIP5", "percent_off": None, "amount_off": 5.0, "active": True, "max_uses": 120, "used_count": 10, "starts_at": now - timedelta(days=2), "ends_at": now + timedelta(days=10)},
            {"code": "SPRING15", "percent_off": 15, "amount_off": None, "active": False, "max_uses": 100, "used_count": 100, "starts_at": now - timedelta(days=90), "ends_at": now - timedelta(days=1)},
        ]
        coupons = [
            OwnerbotDemoCoupon(
                code=item["code"],
                percent_off=item["percent_off"],
                amount_off=item["amount_off"],
                active=item["active"],
                max_uses=item["max_uses"],
                used_count=item["used_count"],
                starts_at=item["starts_at"],
                ends_at=item["ends_at"],
            )
            for item in coupon_seeds
            if item["code"] not in existing_coupon_codes
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
        session.add_all(products)
        session.add_all(order_items)
        session.add_all(coupons)
        await session.commit()
