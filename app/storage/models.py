from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import Date, DateTime, Integer, String, Numeric, Text, func, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OwnerbotActionLog(Base):
    __tablename__ = "ownerbot_action_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)


class OwnerbotAuditEvent(Base):
    __tablename__ = "ownerbot_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class OwnerbotDemoOrder(Base):
    __tablename__ = "ownerbot_demo_orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    flagged: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    flagged_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OwnerbotDemoKpiDaily(Base):
    __tablename__ = "ownerbot_demo_kpi_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    revenue_gross: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    revenue_net: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    orders_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    orders_created: Mapped[int] = mapped_column(Integer, nullable=False)
    aov: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)


class OwnerbotDemoChatThread(Base):
    __tablename__ = "ownerbot_demo_chat_threads"

    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    open: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    last_customer_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_manager_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
