from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.time import utcnow
from app.storage.models import OwnerbotDemoOrder
from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning, ToolActor


class Payload(BaseModel):
    order_id: str = Field(..., min_length=1)
    reason: str = Field("", min_length=0, max_length=300)
    dry_run: bool = True


async def handle(
    payload: Payload,
    correlation_id: str,
    session,
    actor: ToolActor | None = None,
) -> ToolResponse:
    stmt = select(OwnerbotDemoOrder).where(OwnerbotDemoOrder.order_id == payload.order_id)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="NOT_FOUND",
            message=f"Order {payload.order_id} not found.",
        )

    reason_value = payload.reason or ""
    provenance = ToolProvenance(
        sources=[f"ownerbot_demo_orders:{order.order_id}", "local_demo"],
        window=None,
        filters_hash="demo",
    )

    if payload.dry_run:
        data = {
            "dry_run": True,
            "will_update": {"order_id": order.order_id, "flagged": True, "reason": reason_value},
            "note": "Требует подтверждения",
        }
        return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)

    if order.flagged and (order.flag_reason or "") == reason_value:
        warning = ToolWarning(code="ALREADY_FLAGGED", message="Order already flagged with the same reason.")
        data = {"order_id": order.order_id, "flagged": True, "reason": reason_value}
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data=data,
            provenance=provenance,
            warnings=[warning],
        )

    order.flagged = True
    order.flag_reason = reason_value
    order.flagged_at = utcnow()
    order.flagged_by = actor.owner_user_id if actor else None
    await session.commit()

    data = {"order_id": order.order_id, "flagged": True, "reason": reason_value}
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
