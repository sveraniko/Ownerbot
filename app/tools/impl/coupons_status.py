from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy import select

from app.core.settings import get_settings
from app.core.time import utcnow
from app.storage.models import OwnerbotDemoCoupon
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode != "DEMO":
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="UPSTREAM_NOT_IMPLEMENTED",
            message="SIS coupon status endpoint is not implemented yet. Use DEMO or implement SIS side first.",
        )

    rows = (await session.execute(select(OwnerbotDemoCoupon).order_by(OwnerbotDemoCoupon.used_count.desc()))).scalars().all()
    now = utcnow()
    soon = now + timedelta(days=7)
    active = [item for item in rows if item.active]
    expiring_soon = [item for item in active if item.ends_at and now <= item.ends_at <= soon]

    top_active = [
        {"code": item.code, "used_count": item.used_count, "percent_off": item.percent_off, "amount_off": float(item.amount_off or 0)}
        for item in active[:5]
    ]
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"total_active": len(active), "expiring_soon": len(expiring_soon), "top_active": top_active},
        provenance=ToolProvenance(sources=["ownerbot_demo_coupons", "local_demo"], filters_hash="coupons_status", window={"scope": "snapshot", "type": "snapshot"}),
    )
