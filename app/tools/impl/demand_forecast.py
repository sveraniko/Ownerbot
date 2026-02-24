from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.core.time import utcnow
from app.tools.contracts import ToolProvenance, ToolResponse
from app.tools.impl._forecasting import (
    build_daily_qty_series,
    confidence_from,
    forecast_ses,
    forecast_sma,
    list_products,
)


class Payload(BaseModel):
    horizon_days: int = Field(default=7, ge=1, le=60)
    history_days: int = Field(default=30, ge=7, le=120)
    method: Literal["sma", "ses"] = "sma"
    window_days: int = Field(default=14, ge=3, le=60)
    alpha: float = Field(default=0.35, ge=0.05, le=0.95)
    limit: int = Field(default=10, ge=1, le=50)
    include_categories: list[str] | None = None


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode != "DEMO":
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="UPSTREAM_NOT_IMPLEMENTED",
            message="Forecast tools are DEMO-only пока нет SIS sales aggregates endpoint.",
        )

    products = await list_products(session, payload.include_categories)
    series_map = await build_daily_qty_series(
        session=session,
        history_days=payload.history_days,
        include_categories=payload.include_categories,
    )

    items: list[dict[str, object]] = []
    for product in products:
        series = series_map.get(product.product_id, [0.0] * payload.history_days)
        avg_daily_qty = sum(series) / len(series) if series else 0.0
        forecast_daily_qty = forecast_sma(series, payload.window_days) if payload.method == "sma" else forecast_ses(series, payload.alpha)
        forecast_total_qty = forecast_daily_qty * payload.horizon_days
        nonzero_days = sum(1 for value in series if value > 0)
        confidence = confidence_from(series, payload.history_days)

        notes: list[str] = []
        if nonzero_days == 0:
            notes.append("no sales history")
        if confidence == "LOW":
            notes.append("low confidence")

        items.append(
            {
                "product_id": product.product_id,
                "title": product.title,
                "category": product.category,
                "stock_qty": product.stock_qty,
                "avg_daily_qty": round(avg_daily_qty, 2),
                "forecast_daily_qty": round(forecast_daily_qty, 2),
                "forecast_total_qty": round(forecast_total_qty, 2),
                "nonzero_days": nonzero_days,
                "confidence": confidence,
                "notes": notes,
            }
        )

    items.sort(key=lambda row: (-float(row["forecast_total_qty"]), str(row["product_id"])))
    data = {
        "horizon_days": payload.horizon_days,
        "history_days": payload.history_days,
        "method": payload.method,
        "window_days": payload.window_days,
        "alpha": payload.alpha,
        "limit": payload.limit,
        "include_categories": payload.include_categories or [],
        "items": items[: payload.limit],
    }

    now = utcnow()
    start_day = now.date() - timedelta(days=payload.history_days - 1)
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data=data,
        provenance=ToolProvenance(
            sources=["ownerbot_demo_orders", "ownerbot_demo_order_items", "ownerbot_demo_products", "local_demo"],
            window={"scope": "demand", "type": "rolling", "from": start_day.isoformat(), "to": now.date().isoformat(), "history_days": payload.history_days},
            filters_hash="demo",
        ),
    )
