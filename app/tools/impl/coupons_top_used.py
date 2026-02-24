from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.settings import get_settings
from app.storage.models import OwnerbotDemoCoupon
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    limit: int = Field(5, ge=1, le=20)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode != "DEMO":
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="UPSTREAM_NOT_IMPLEMENTED",
            message="SIS coupon top-used endpoint is not implemented yet. Use DEMO or implement SIS side first.",
        )

    rows = (
        await session.execute(select(OwnerbotDemoCoupon).order_by(OwnerbotDemoCoupon.used_count.desc(), OwnerbotDemoCoupon.code.asc()))
    ).scalars().all()
    top = [
        {
            "rank": idx + 1,
            "code": item.code,
            "used_count": item.used_count,
            "active": item.active,
            "percent_off": item.percent_off,
            "amount_off": float(item.amount_off or 0),
        }
        for idx, item in enumerate(rows[: payload.limit])
    ]

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"rows": top},
        provenance=ToolProvenance(sources=["ownerbot_demo_coupons", "local_demo"], filters_hash=f"coupons_top_used:{payload.limit}", window={"scope": "snapshot", "type": "snapshot"}),
    )
