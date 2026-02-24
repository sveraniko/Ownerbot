from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.settings import get_settings
from app.storage.models import OwnerbotDemoOrder
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    order_id: str = Field(..., min_length=1)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode != "DEMO":
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="UPSTREAM_NOT_IMPLEMENTED",
            message="Orders tools are not wired to SIS Actions API yet (draft contract only).",
        )

    stmt = select(OwnerbotDemoOrder).where(OwnerbotDemoOrder.order_id == payload.order_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="NOT_FOUND",
            message=f"Order {payload.order_id} not found.",
        )
    data = {
        "order_id": row.order_id,
        "status": row.status,
        "amount": float(row.amount),
        "currency": row.currency,
        "customer_id": row.customer_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "customer_phone": row.customer_phone,
        "payment_status": row.payment_status,
        "paid_at": row.paid_at.isoformat() if row.paid_at else None,
        "shipping_status": row.shipping_status,
        "ship_due_at": row.ship_due_at.isoformat() if row.ship_due_at else None,
        "shipped_at": row.shipped_at.isoformat() if row.shipped_at else None,
    }
    provenance = ToolProvenance(
        sources=[f"ownerbot_demo_orders:{row.order_id}", "local_ownerbot"],
        window={"scope": "demo_order", "type": "detail"},
        filters_hash="demo",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
