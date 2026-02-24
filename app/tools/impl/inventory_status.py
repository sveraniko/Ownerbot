from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.storage.models import OwnerbotDemoProduct
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    low_stock_lte: int = Field(5, ge=0, le=999)
    limit: int = Field(20, ge=1, le=50)
    section: Literal[
        "all",
        "out_of_stock",
        "low_stock",
        "missing_photo",
        "missing_price",
        "missing_video",
        "return_flags",
        "unpublished",
    ] = "all"


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    rows = (await session.execute(select(OwnerbotDemoProduct).order_by(OwnerbotDemoProduct.product_id.asc()))).scalars().all()

    def serialize(items: list[OwnerbotDemoProduct]) -> list[dict[str, object]]:
        return [
            {
                "product_id": row.product_id,
                "title": row.title,
                "category": row.category,
                "stock_qty": row.stock_qty,
                "price": float(row.price),
            }
            for row in items[: payload.limit]
        ]

    buckets = {
        "out_of_stock": [row for row in rows if row.published and row.stock_qty == 0],
        "low_stock": [row for row in rows if row.published and 0 < row.stock_qty <= payload.low_stock_lte],
        "missing_photo": [row for row in rows if row.published and not row.has_photo],
        "missing_price": [row for row in rows if row.published and float(row.price) <= 0],
        "missing_video": [row for row in rows if row.published and not row.has_video],
        "return_flags": [row for row in rows if row.return_flagged],
        "unpublished": [row for row in rows if not row.published],
    }
    counts = {name: len(items) for name, items in buckets.items()}

    if payload.section == "all":
        data = {
            "counts": counts,
            **{name: serialize(items) for name, items in buckets.items()},
        }
    else:
        data = {
            "header": {
                "section": payload.section,
                "count": counts[payload.section],
                "limit": payload.limit,
            },
            payload.section: serialize(buckets[payload.section]),
        }

    provenance = ToolProvenance(
        sources=["ownerbot_demo_products", "local_demo"],
        window={"scope": "demo_catalog", "type": "snapshot"},
        filters_hash=f"low_stock_lte:{payload.low_stock_lte};limit:{payload.limit};section:{payload.section}",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
