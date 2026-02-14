from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_, select

from app.core.settings import get_settings
from app.core.time import utcnow
from app.storage.models import OwnerbotDemoOrder
from app.tools.contracts import ToolProvenance, ToolResponse

PresetName = Literal["stuck", "late_ship", "payment_issues"]


class OrdersSearchPayload(BaseModel):
    q: str | None = None
    status: str | None = None
    preset: PresetName | None = None
    flagged: bool | None = None
    limit: int = Field(default=20, ge=1, le=200)
    since_hours: int | None = Field(default=None, ge=1, le=720)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("status must be non-empty")
        return normalized


def _pending_hours_threshold(payload: OrdersSearchPayload) -> int:
    return payload.since_hours if payload.since_hours is not None else 2


def apply_orders_filters(stmt, payload: OrdersSearchPayload, now):
    if payload.preset == "stuck":
        pending_cutoff = now - timedelta(hours=6)
        stmt = stmt.where(
            or_(
                OwnerbotDemoOrder.status == "stuck",
                and_(
                    or_(
                        OwnerbotDemoOrder.payment_status == "pending",
                        OwnerbotDemoOrder.payment_status.is_(None),
                    ),
                    OwnerbotDemoOrder.created_at <= pending_cutoff,
                ),
            )
        )
    elif payload.preset == "late_ship":
        stmt = stmt.where(
            and_(
                OwnerbotDemoOrder.payment_status == "paid",
                or_(
                    OwnerbotDemoOrder.shipping_status != "shipped",
                    OwnerbotDemoOrder.shipped_at.is_(None),
                ),
                OwnerbotDemoOrder.ship_due_at.is_not(None),
                OwnerbotDemoOrder.ship_due_at < now,
            )
        )
    elif payload.preset == "payment_issues":
        pending_cutoff = now - timedelta(hours=_pending_hours_threshold(payload))
        stmt = stmt.where(
            or_(
                OwnerbotDemoOrder.payment_status == "failed",
                and_(
                    OwnerbotDemoOrder.payment_status == "pending",
                    OwnerbotDemoOrder.created_at <= pending_cutoff,
                ),
            )
        )

    if payload.status:
        stmt = stmt.where(OwnerbotDemoOrder.status == payload.status)

    if payload.flagged is not None:
        stmt = stmt.where(OwnerbotDemoOrder.flagged == payload.flagged)

    if payload.q:
        term = f"%{payload.q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(OwnerbotDemoOrder.customer_phone, "")).like(term),
                func.lower(OwnerbotDemoOrder.order_id).like(term),
                func.lower(OwnerbotDemoOrder.customer_id).like(term),
            )
        )

    return stmt


def build_applied_filters(payload: OrdersSearchPayload) -> dict[str, object]:
    return {
        "preset": payload.preset,
        "status": payload.status,
        "flagged": payload.flagged,
        "q": payload.q,
        "limit": payload.limit,
    }


def _filters_hash(filters: dict[str, object]) -> str:
    raw = json.dumps(filters, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


async def handle(payload: OrdersSearchPayload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode != "DEMO":
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="UPSTREAM_NOT_IMPLEMENTED",
            message="Orders tools are not wired to SIS Actions API yet (draft contract only).",
        )

    now = utcnow()
    stmt = apply_orders_filters(select(OwnerbotDemoOrder), payload, now)
    stmt = stmt.order_by(OwnerbotDemoOrder.created_at.desc()).limit(payload.limit)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    applied_filters = build_applied_filters(payload)
    data = {
        "count": len(rows),
        "items": [
            {
                "order_id": row.order_id,
                "status": row.status,
                "amount": float(row.amount),
                "currency": row.currency,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "flagged": row.flagged,
                "customer_phone": row.customer_phone,
                "payment_status": row.payment_status,
                "shipping_status": row.shipping_status,
            }
            for row in rows
        ],
        "applied_filters": applied_filters,
    }
    provenance = ToolProvenance(
        sources=["local_ownerbot"],
        window=None,
        filters_hash=_filters_hash(applied_filters),
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
