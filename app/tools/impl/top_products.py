from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select

from app.core.time import utcnow
from app.storage.models import OwnerbotDemoOrder, OwnerbotDemoOrderItem, OwnerbotDemoProduct
from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning


class Payload(BaseModel):
    days: int = Field(7, ge=1, le=60)
    metric: Literal["revenue", "qty"] = "revenue"
    direction: Literal["top", "bottom"] = "top"
    group_by: Literal["product", "category"] = "product"
    limit: int = Field(10, ge=1, le=30)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    now = utcnow()
    window_start = now - timedelta(days=payload.days)

    paid_filter = or_(OwnerbotDemoOrder.status == "paid", OwnerbotDemoOrder.payment_status == "paid")
    revenue_expr = func.sum(OwnerbotDemoOrderItem.qty * OwnerbotDemoOrderItem.unit_price)
    qty_expr = func.sum(OwnerbotDemoOrderItem.qty)

    if payload.group_by == "product":
        stmt = (
            select(
                OwnerbotDemoOrderItem.product_id.label("key"),
                OwnerbotDemoProduct.title.label("title"),
                OwnerbotDemoProduct.category.label("category"),
                qty_expr.label("qty"),
                revenue_expr.label("revenue"),
            )
            .join(OwnerbotDemoOrder, OwnerbotDemoOrder.order_id == OwnerbotDemoOrderItem.order_id)
            .join(OwnerbotDemoProduct, OwnerbotDemoProduct.product_id == OwnerbotDemoOrderItem.product_id)
            .where(and_(OwnerbotDemoOrder.created_at >= window_start, paid_filter))
            .group_by(OwnerbotDemoOrderItem.product_id, OwnerbotDemoProduct.title, OwnerbotDemoProduct.category)
        )
    else:
        stmt = (
            select(
                OwnerbotDemoProduct.category.label("key"),
                OwnerbotDemoProduct.category.label("title"),
                OwnerbotDemoProduct.category.label("category"),
                qty_expr.label("qty"),
                revenue_expr.label("revenue"),
            )
            .join(OwnerbotDemoOrder, OwnerbotDemoOrder.order_id == OwnerbotDemoOrderItem.order_id)
            .join(OwnerbotDemoProduct, OwnerbotDemoProduct.product_id == OwnerbotDemoOrderItem.product_id)
            .where(and_(OwnerbotDemoOrder.created_at >= window_start, paid_filter))
            .group_by(OwnerbotDemoProduct.category)
        )

    rows = (await session.execute(stmt)).all()
    warnings: list[ToolWarning] = []
    if not rows:
        warnings.append(ToolWarning(code="NO_DATA", message="No paid order items found for selected window."))
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"rows": [], "totals": {"total_revenue": 0.0, "total_qty": 0}},
            provenance=ToolProvenance(
                sources=["ownerbot_demo_orders", "ownerbot_demo_order_items", "ownerbot_demo_products", "local_demo"],
                window={"start": window_start.isoformat(), "end": now.isoformat(), "days": payload.days},
                filters_hash=f"metric:{payload.metric};group_by:{payload.group_by};direction:{payload.direction}",
            ),
            warnings=warnings,
        )

    serialized = [
        {
            "key": row.key,
            "title": row.title,
            "category": row.category,
            "qty": int(row.qty or 0),
            "revenue": float(row.revenue or Decimal("0")),
        }
        for row in rows
    ]

    reverse = payload.direction == "top"
    sort_key = (lambda item: item["revenue"]) if payload.metric == "revenue" else (lambda item: item["qty"])
    serialized.sort(key=sort_key, reverse=reverse)

    ranked = [
        {
            "rank": idx + 1,
            "key": item["key"],
            "title": item["title"],
            "category": item["category"],
            "qty": item["qty"],
            "revenue": round(item["revenue"], 2),
        }
        for idx, item in enumerate(serialized[: payload.limit])
    ]

    totals = {
        "total_revenue": round(sum(item["revenue"] for item in serialized), 2),
        "total_qty": int(sum(item["qty"] for item in serialized)),
    }
    provenance = ToolProvenance(
        sources=["ownerbot_demo_orders", "ownerbot_demo_order_items", "ownerbot_demo_products", "local_demo"],
        window={"start": window_start.isoformat(), "end": now.isoformat(), "days": payload.days},
        filters_hash=f"metric:{payload.metric};group_by:{payload.group_by};direction:{payload.direction}",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data={"rows": ranked, "totals": totals}, provenance=provenance)
