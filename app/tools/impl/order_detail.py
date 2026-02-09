from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.storage.models import OwnerbotDemoOrder
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    order_id: str = Field(..., min_length=1)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    stmt = select(OwnerbotDemoOrder).where(OwnerbotDemoOrder.order_id == payload.order_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return ToolResponse.error(
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
    }
    provenance = ToolProvenance(
        sources=[f"ownerbot_demo_orders:{row.order_id}", "local_demo"],
        window=None,
        filters_hash="demo",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
