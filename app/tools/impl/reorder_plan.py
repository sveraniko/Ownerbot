from __future__ import annotations

import math
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

_SMALL_EPS = 1e-9


class Payload(BaseModel):
    horizon_days: int = Field(default=14, ge=1, le=90)
    history_days: int = Field(default=30, ge=7, le=120)
    method: Literal["sma", "ses"] = "sma"
    window_days: int = Field(default=14, ge=3, le=60)
    alpha: float = Field(default=0.35, ge=0.05, le=0.95)
    lead_time_days: int = Field(default=14, ge=1, le=90)
    safety_stock_days: int = Field(default=7, ge=0, le=90)
    limit: int = Field(default=20, ge=1, le=100)
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
        forecast_daily_qty = forecast_sma(series, payload.window_days) if payload.method == "sma" else forecast_ses(series, payload.alpha)
        forecast_total_qty = forecast_daily_qty * payload.horizon_days
        lead_time_demand = forecast_daily_qty * payload.lead_time_days
        safety_stock_units = forecast_daily_qty * payload.safety_stock_days
        reorder_point = lead_time_demand + safety_stock_units
        reorder_needed = product.stock_qty <= reorder_point and forecast_daily_qty > 0
        stock_cover_days = product.stock_qty / max(forecast_daily_qty, _SMALL_EPS)

        target_days = payload.lead_time_days + payload.safety_stock_days + payload.horizon_days
        target_stock = forecast_daily_qty * target_days
        recommended_order_qty = max(0, math.ceil(target_stock - product.stock_qty))
        confidence = confidence_from(series, payload.history_days)

        notes: list[str] = []
        if all(value <= 0 for value in series):
            notes.append("no sales history")
        if confidence == "LOW":
            notes.append("low confidence")

        items.append(
            {
                "product_id": product.product_id,
                "title": product.title,
                "category": product.category,
                "stock_qty": product.stock_qty,
                "forecast_daily_qty": round(forecast_daily_qty, 2),
                "reorder_point": round(reorder_point, 2),
                "recommended_order_qty": int(recommended_order_qty),
                "stock_cover_days": round(stock_cover_days, 2),
                "forecast_total_qty": round(forecast_total_qty, 2),
                "reorder_needed": reorder_needed,
                "confidence": confidence,
                "notes": notes,
            }
        )

    items.sort(key=lambda row: (not bool(row["reorder_needed"]), float(row["stock_cover_days"]), -float(row["forecast_total_qty"])))
    data = {
        "horizon_days": payload.horizon_days,
        "history_days": payload.history_days,
        "method": payload.method,
        "window_days": payload.window_days,
        "alpha": payload.alpha,
        "lead_time_days": payload.lead_time_days,
        "safety_stock_days": payload.safety_stock_days,
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
            window={"from": start_day.isoformat(), "to": now.date().isoformat(), "history_days": payload.history_days},
            filters_hash="demo",
        ),
    )
