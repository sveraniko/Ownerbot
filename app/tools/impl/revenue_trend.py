from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.storage.models import OwnerbotDemoKpiDaily
from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning


class Payload(BaseModel):
    days: int = Field(7, ge=1, le=60)
    end_day: date | None = None


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    end_day = payload.end_day or date.today()
    start_day = end_day - timedelta(days=payload.days - 1)

    stmt = (
        select(OwnerbotDemoKpiDaily)
        .where(OwnerbotDemoKpiDaily.day >= start_day)
        .where(OwnerbotDemoKpiDaily.day <= end_day)
        .order_by(OwnerbotDemoKpiDaily.day.asc())
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    series = [
        {
            "day": row.day.isoformat(),
            "revenue_gross": float(row.revenue_gross),
            "revenue_net": float(row.revenue_net),
            "orders_paid": row.orders_paid,
            "aov": float(row.aov),
        }
        for row in rows
    ]

    totals = {
        "revenue_gross": float(sum(row.revenue_gross for row in rows)),
        "revenue_net": float(sum(row.revenue_net for row in rows)),
        "orders_paid": int(sum(row.orders_paid for row in rows)),
    }

    warnings: list[ToolWarning] = []
    delta_vs_prev_window: dict | None = None

    if len(rows) < payload.days:
        warnings.append(
            ToolWarning(
                code="INSUFFICIENT_DATA",
                message="Not enough KPI rows for the requested window.",
            )
        )

    prev_start = start_day - timedelta(days=payload.days)
    prev_end = start_day - timedelta(days=1)
    prev_stmt = (
        select(OwnerbotDemoKpiDaily)
        .where(OwnerbotDemoKpiDaily.day >= prev_start)
        .where(OwnerbotDemoKpiDaily.day <= prev_end)
    )
    prev_result = await session.execute(prev_stmt)
    prev_rows = prev_result.scalars().all()

    if len(prev_rows) >= payload.days:
        prev_totals = {
            "revenue_gross": float(sum(row.revenue_gross for row in prev_rows)),
            "orders_paid": int(sum(row.orders_paid for row in prev_rows)),
        }
        if prev_totals["revenue_gross"] > 0 and prev_totals["orders_paid"] > 0:
            delta_vs_prev_window = {
                "revenue_gross_pct": round(
                    ((totals["revenue_gross"] - prev_totals["revenue_gross"]) / prev_totals["revenue_gross"]) * 100,
                    2,
                ),
                "orders_paid_pct": round(
                    ((totals["orders_paid"] - prev_totals["orders_paid"]) / prev_totals["orders_paid"]) * 100,
                    2,
                ),
            }
        else:
            warnings.append(
                ToolWarning(
                    code="PREV_WINDOW_ZERO",
                    message="Previous window totals are zero; delta is unavailable.",
                )
            )
    else:
        warnings.append(
            ToolWarning(
                code="PREV_WINDOW_MISSING",
                message="Previous window data is not available for comparison.",
            )
        )

    data = {
        "days": payload.days,
        "end_day": end_day.isoformat(),
        "series": series,
        "totals": totals,
        "delta_vs_prev_window": delta_vs_prev_window,
    }
    provenance = ToolProvenance(
        sources=[f"ownerbot_demo_kpi_daily:{start_day.isoformat()}..{end_day.isoformat()}", "local_demo"],
        window={"start_day": start_day.isoformat(), "end_day": end_day.isoformat(), "days": payload.days},
        filters_hash="demo",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance, warnings=warnings)
