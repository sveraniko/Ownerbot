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
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
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
        "ownerbot_demo_chat_threads",
        sa.Column("thread_id", sa.String(length=64), primary_key=True),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("open", sa.Boolean(), nullable=False),
        sa.Column("last_customer_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_manager_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ownerbot_demo_chat_threads")
    op.drop_table("ownerbot_demo_kpi_daily")
    op.drop_table("ownerbot_demo_orders")
    op.drop_table("ownerbot_audit_events")
    op.drop_table("ownerbot_action_log")
