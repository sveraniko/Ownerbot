"""ownerbot baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2024-03-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ownerbot_action_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("tool", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
    )
    op.create_table(
        "ownerbot_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_table(
        "ownerbot_demo_orders",
        sa.Column("order_id", sa.String(length=64), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("customer_phone", sa.String(length=32), nullable=True),
        sa.Column("payment_status", sa.String(length=32), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipping_status", sa.String(length=32), nullable=True),
        sa.Column("ship_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("flag_reason", sa.Text(), nullable=True),
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("flagged_by", sa.Integer(), nullable=True),
    )
    op.create_table(
        "ownerbot_demo_kpi_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("revenue_gross", sa.Numeric(12, 2), nullable=False),
        sa.Column("revenue_net", sa.Numeric(12, 2), nullable=False),
        sa.Column("orders_paid", sa.Integer(), nullable=False),
        sa.Column("orders_created", sa.Integer(), nullable=False),
        sa.Column("aov", sa.Numeric(12, 2), nullable=False),
    )
    op.create_table(
        "ownerbot_demo_products",
        sa.Column("product_id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("stock_qty", sa.Integer(), nullable=False),
        sa.Column("has_photo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ownerbot_demo_order_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ownerbot_demo_chat_threads",
        sa.Column("thread_id", sa.String(length=64), primary_key=True),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("open", sa.Boolean(), nullable=False),
        sa.Column("last_customer_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_manager_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(
        "idx_ownerbot_audit_events_occurred_at",
        "ownerbot_audit_events",
        ["occurred_at"],
    )
    op.create_index(
        "idx_ownerbot_audit_events_event_type_occurred_at",
        "ownerbot_audit_events",
        ["event_type", "occurred_at"],
    )
    op.create_index(
        "idx_ownerbot_audit_events_correlation_id",
        "ownerbot_audit_events",
        ["correlation_id"],
    )

    op.create_index(
        "idx_ownerbot_action_log_status_committed_at",
        "ownerbot_action_log",
        ["status", "committed_at"],
    )
    op.create_index(
        "idx_ownerbot_action_log_tool_committed_at",
        "ownerbot_action_log",
        ["tool", "committed_at"],
    )
    op.create_index(
        "idx_ownerbot_action_log_correlation_id",
        "ownerbot_action_log",
        ["correlation_id"],
    )

    op.create_index(
        "idx_ownerbot_demo_orders_status_created_at",
        "ownerbot_demo_orders",
        ["status", "created_at"],
    )

    op.create_index(
        "idx_ownerbot_demo_orders_customer_phone",
        "ownerbot_demo_orders",
        ["customer_phone"],
    )

    op.create_index(
        "idx_ownerbot_demo_products_category",
        "ownerbot_demo_products",
        ["category"],
    )
    op.create_index(
        "idx_ownerbot_demo_products_published",
        "ownerbot_demo_products",
        ["published"],
    )
    op.create_index(
        "idx_ownerbot_demo_products_stock_qty",
        "ownerbot_demo_products",
        ["stock_qty"],
    )
    op.create_index(
        "idx_ownerbot_demo_order_items_order_id",
        "ownerbot_demo_order_items",
        ["order_id"],
    )
    op.create_index(
        "idx_ownerbot_demo_order_items_product_id",
        "ownerbot_demo_order_items",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_ownerbot_demo_order_items_product_id", table_name="ownerbot_demo_order_items")
    op.drop_index("idx_ownerbot_demo_order_items_order_id", table_name="ownerbot_demo_order_items")
    op.drop_index("idx_ownerbot_demo_products_stock_qty", table_name="ownerbot_demo_products")
    op.drop_index("idx_ownerbot_demo_products_published", table_name="ownerbot_demo_products")
    op.drop_index("idx_ownerbot_demo_products_category", table_name="ownerbot_demo_products")
    op.drop_index("idx_ownerbot_demo_orders_customer_phone", table_name="ownerbot_demo_orders")
    op.drop_index("idx_ownerbot_demo_orders_status_created_at", table_name="ownerbot_demo_orders")
    op.drop_index("idx_ownerbot_action_log_correlation_id", table_name="ownerbot_action_log")
    op.drop_index("idx_ownerbot_action_log_tool_committed_at", table_name="ownerbot_action_log")
    op.drop_index("idx_ownerbot_action_log_status_committed_at", table_name="ownerbot_action_log")
    op.drop_index("idx_ownerbot_audit_events_correlation_id", table_name="ownerbot_audit_events")
    op.drop_index("idx_ownerbot_audit_events_event_type_occurred_at", table_name="ownerbot_audit_events")
    op.drop_index("idx_ownerbot_audit_events_occurred_at", table_name="ownerbot_audit_events")
    op.drop_table("ownerbot_demo_chat_threads")
    op.drop_table("ownerbot_demo_order_items")
    op.drop_table("ownerbot_demo_products")
    op.drop_table("ownerbot_demo_kpi_daily")
    op.drop_table("ownerbot_demo_orders")
    op.drop_table("ownerbot_audit_events")
    op.drop_table("ownerbot_action_log")
