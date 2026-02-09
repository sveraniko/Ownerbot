from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select

from app.tools.contracts import ToolProvenance, ToolResponse
from app.storage.models import OwnerbotDemoOrder


class OrdersSearchPayload(BaseModel):
    status: str | None = None
    limit: int = 5


async def handle(payload: OrdersSearchPayload, correlation_id: str, session) -> ToolResponse:
    stmt = select(OwnerbotDemoOrder)
    if payload.status:
        stmt = stmt.where(OwnerbotDemoOrder.status == payload.status)
    stmt = stmt.order_by(OwnerbotDemoOrder.created_at.desc()).limit(payload.limit)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    data = {
        "count": len(rows),
        "orders": [
            {
                "order_id": row.order_id,
                "status": row.status,
                "amount": float(row.amount),
                "currency": row.currency,
                "customer_id": row.customer_id,
            }
            for row in rows
        ],
    }
    provenance = ToolProvenance(
        sources=["ownerbot_demo_orders", "local_demo"],
        window=None,
        filters_hash="demo",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
