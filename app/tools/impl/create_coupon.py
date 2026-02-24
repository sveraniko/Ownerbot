from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.core.settings import get_settings
from app.storage.models import OwnerbotDemoCoupon
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    dry_run: bool = True
    code: str = Field(min_length=3, max_length=64)
    percent_off: int | None = Field(default=None, ge=1, le=95)
    amount_off: float | None = Field(default=None, ge=0)
    active: bool = True
    max_uses: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_discount_shape(self) -> "Payload":
        if (self.percent_off is None) == (self.amount_off is None):
            raise ValueError("Provide exactly one of percent_off or amount_off")
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode != "DEMO":
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="UPSTREAM_NOT_IMPLEMENTED",
            message="SIS endpoint for coupon management is not implemented yet. Use DEMO or implement SIS side first.",
        )

    code = payload.code.strip().upper()
    existing = (await session.execute(select(OwnerbotDemoCoupon).where(OwnerbotDemoCoupon.code == code))).scalar_one_or_none()
    operation = "update" if existing else "create"

    preview = {
        "status": "ok",
        "operation": operation,
        "code": code,
        "active": payload.active,
        "percent_off": payload.percent_off,
        "amount_off": payload.amount_off,
        "max_uses": payload.max_uses,
    }
    if payload.dry_run:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data=preview,
            provenance=ToolProvenance(sources=["ownerbot_demo_coupons", "local_demo"], filters_hash="create_coupon", window={"scope": "snapshot", "type": "snapshot"}),
        )

    if existing:
        existing.percent_off = payload.percent_off
        existing.amount_off = payload.amount_off
        existing.active = payload.active
        existing.max_uses = payload.max_uses
        existing.starts_at = payload.starts_at
        existing.ends_at = payload.ends_at
        await session.commit()
        coupon_id = existing.id
    else:
        coupon = OwnerbotDemoCoupon(
            code=code,
            percent_off=payload.percent_off,
            amount_off=payload.amount_off,
            active=payload.active,
            max_uses=payload.max_uses,
            used_count=0,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
        session.add(coupon)
        await session.commit()
        coupon_id = coupon.id

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"status": "committed", "operation": operation, "coupon_id": coupon_id, "code": code},
        provenance=ToolProvenance(sources=["ownerbot_demo_coupons", "local_demo"], filters_hash="create_coupon", window={"scope": "snapshot", "type": "snapshot"}),
    )
