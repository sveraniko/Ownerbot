from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.core.settings import get_settings
from app.storage.models import OwnerbotDemoProduct
from app.tools.contracts import ToolProvenance, ToolResponse


_MAX_DELTA_ABS_NO_FORCE = Decimal("100")


class Payload(BaseModel):
    dry_run: bool = True
    product_ids: list[str]
    mode: Literal["set", "delta_percent", "delta_abs"]
    value: float
    rounding: Literal["none", "int", "0.5", "0.99"] = "none"
    force: bool = False

    @model_validator(mode="after")
    def validate_scope(self) -> "Payload":
        if not self.product_ids:
            raise ValueError("product_ids must contain at least one product id")
        return self


def _apply_rounding(value: Decimal, rounding: str) -> Decimal:
    if rounding == "none":
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounding == "int":
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if rounding == "0.5":
        return (value * Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / Decimal("2")
    if rounding == "0.99":
        base = int(value)
        return Decimal(str(max(base, 0))) + Decimal("0.99")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calc_new_price(old_price: Decimal, mode: str, value: Decimal, rounding: str) -> Decimal:
    if mode == "set":
        candidate = value
    elif mode == "delta_percent":
        candidate = old_price * (Decimal("1") + value / Decimal("100"))
    else:
        candidate = old_price + value
    if candidate < Decimal("0"):
        candidate = Decimal("0")
    return _apply_rounding(candidate, rounding)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode != "DEMO":
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="UPSTREAM_NOT_IMPLEMENTED",
            message="SIS endpoint for price update is not implemented yet. Use DEMO or implement SIS side first.",
        )

    value = Decimal(str(payload.value))
    if payload.mode == "delta_percent" and abs(value) > Decimal("30") and not payload.force:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="FORCE_REQUIRED",
            message="delta_percent above 30% requires force=true.",
        )
    if payload.mode == "delta_abs" and abs(value) > _MAX_DELTA_ABS_NO_FORCE and not payload.force:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="FORCE_REQUIRED",
            message="delta_abs above 100 requires force=true.",
        )

    rows = (
        await session.execute(
            select(OwnerbotDemoProduct).where(OwnerbotDemoProduct.product_id.in_(payload.product_ids)).order_by(OwnerbotDemoProduct.product_id.asc())
        )
    ).scalars().all()
    if not rows:
        return ToolResponse.fail(correlation_id=correlation_id, code="NOT_FOUND", message="No products found for provided product_ids.")

    preview_rows: list[dict[str, object]] = []
    changed_rows: list[OwnerbotDemoProduct] = []
    total_before = Decimal("0")
    total_after = Decimal("0")

    for row in rows:
        old_price = Decimal(str(row.price))
        new_price = _calc_new_price(old_price, payload.mode, value, payload.rounding)
        total_before += old_price
        total_after += new_price
        changed = new_price != old_price
        if changed:
            changed_rows.append(row)
        preview_rows.append(
            {
                "product_id": row.product_id,
                "title": row.title,
                "old_price": float(old_price),
                "new_price": float(new_price),
                "changed": changed,
            }
        )

    if payload.dry_run:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "status": "no_change" if not changed_rows else "ok",
                "would_apply": bool(changed_rows),
                "affected_count": len(changed_rows),
                "total_before": float(total_before.quantize(Decimal("0.01"))),
                "total_after": float(total_after.quantize(Decimal("0.01"))),
                "rows": preview_rows,
            },
            provenance=ToolProvenance(sources=["ownerbot_demo_products", "local_demo"], filters_hash="adjust_price"),
        )

    for row_data, row in zip(preview_rows, rows):
        if row_data["changed"]:
            row.price = row_data["new_price"]
    await session.commit()

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "status": "committed",
            "affected_count": len(changed_rows),
            "rows": preview_rows[:10],
        },
        provenance=ToolProvenance(sources=["ownerbot_demo_products", "local_demo"], filters_hash="adjust_price"),
    )
