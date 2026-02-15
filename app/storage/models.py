from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Numeric, Text, func, Boolean, Index
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


class OwnerNotifySettings(Base):
    __tablename__ = "owner_notify_settings"

    owner_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fx_delta_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    fx_delta_min_percent: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0.25)
    fx_delta_cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    fx_delta_last_notified_rate: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    fx_delta_last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fx_delta_last_seen_sis_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fx_apply_events_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    fx_apply_notify_applied: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    fx_apply_notify_noop: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    fx_apply_notify_failed: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    fx_apply_events_cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    fx_apply_last_seen_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fx_apply_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fx_apply_last_error_notice_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    digest_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    digest_time_local: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")
    digest_tz: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Berlin")
    digest_format: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    digest_include_fx: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    digest_include_ops: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    digest_include_kpi: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    digest_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    weekly_enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    weekly_day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weekly_time_local: Mapped[str] = mapped_column(String(5), nullable=False, default="09:30")
    weekly_tz: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Berlin")
    weekly_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_notice_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OwnerbotDemoOrder(Base):
    __tablename__ = "ownerbot_demo_orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    coupon_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipping_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ship_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class OwnerbotDemoProduct(Base):
    __tablename__ = "ownerbot_demo_products"
    __table_args__ = (
        Index("idx_ownerbot_demo_products_category", "category"),
        Index("idx_ownerbot_demo_products_published", "published"),
        Index("idx_ownerbot_demo_products_stock_qty", "stock_qty"),
    )

    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    stock_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    has_photo: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    has_video: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    return_flagged: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    published: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OwnerbotDemoOrderItem(Base):
    __tablename__ = "ownerbot_demo_order_items"
    __table_args__ = (
        Index("idx_ownerbot_demo_order_items_order_id", "order_id"),
        Index("idx_ownerbot_demo_order_items_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OwnerbotDemoCoupon(Base):
    __tablename__ = "ownerbot_demo_coupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    percent_off: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_off: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
