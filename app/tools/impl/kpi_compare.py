from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.storage.models import OwnerbotDemoKpiDaily
from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning


class Payload(BaseModel):
    preset: Literal["wow", "mom", "custom"] = "wow"
    days: int | None = Field(default=None, ge=1, le=90)
    a_start: date | None = None
    a_end: date | None = None
    b_start: date | None = None
    b_end: date | None = None

    @model_validator(mode="after")
    def validate_custom_window(self) -> "Payload":
        if self.preset != "custom":
            return self
        required = (self.a_start, self.a_end, self.b_start, self.b_end)
        if any(value is None for value in required):
            raise ValueError("Custom preset requires a_start, a_end, b_start and b_end.")
        if self.a_start > self.a_end or self.b_start > self.b_end:
            raise ValueError("Window start must be <= end for both periods.")
        return self


def _safe_pct(delta_abs: float, base: float) -> float | None:
    if base == 0:
        return None
    return round((delta_abs / base) * 100, 2)


def _sum_decimal(rows: list[OwnerbotDemoKpiDaily], attr: str) -> float:
    return float(sum((getattr(row, attr) for row in rows), Decimal("0")))


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    today = date.today()
    warnings: list[ToolWarning] = []

    if payload.preset == "custom":
        a_start = payload.a_start
        a_end = payload.a_end
        b_start = payload.b_start
        b_end = payload.b_end
    else:
        days = payload.days if payload.days is not None else (7 if payload.preset == "wow" else 30)
        a_end = today
        a_start = a_end - timedelta(days=days - 1)
        b_end = a_start - timedelta(days=1)
        b_start = b_end - timedelta(days=days - 1)

    stmt_a = (
        select(OwnerbotDemoKpiDaily)
        .where(OwnerbotDemoKpiDaily.day >= a_start)
        .where(OwnerbotDemoKpiDaily.day <= a_end)
        .order_by(OwnerbotDemoKpiDaily.day.asc())
    )
    stmt_b = (
        select(OwnerbotDemoKpiDaily)
        .where(OwnerbotDemoKpiDaily.day >= b_start)
        .where(OwnerbotDemoKpiDaily.day <= b_end)
        .order_by(OwnerbotDemoKpiDaily.day.asc())
    )

    rows_a = (await session.execute(stmt_a)).scalars().all()
    rows_b = (await session.execute(stmt_b)).scalars().all()

    expected_a_days = (a_end - a_start).days + 1
    expected_b_days = (b_end - b_start).days + 1
    if len(rows_a) < expected_a_days:
        warnings.append(ToolWarning(code="WINDOW_A_MISSING_DAYS", message="Window A has missing KPI daily rows."))
    if len(rows_b) < expected_b_days:
        warnings.append(ToolWarning(code="WINDOW_B_MISSING_DAYS", message="Window B has missing KPI daily rows."))

    totals_a = {
        "revenue_gross_sum": _sum_decimal(rows_a, "revenue_gross"),
        "revenue_net_sum": _sum_decimal(rows_a, "revenue_net"),
        "orders_paid_sum": int(sum(row.orders_paid for row in rows_a)),
        "orders_created_sum": int(sum(row.orders_created for row in rows_a)),
    }
    totals_b = {
        "revenue_gross_sum": _sum_decimal(rows_b, "revenue_gross"),
        "revenue_net_sum": _sum_decimal(rows_b, "revenue_net"),
        "orders_paid_sum": int(sum(row.orders_paid for row in rows_b)),
        "orders_created_sum": int(sum(row.orders_created for row in rows_b)),
    }

    aov_a = round(totals_a["revenue_net_sum"] / max(totals_a["orders_paid_sum"], 1), 2)
    aov_b = round(totals_b["revenue_net_sum"] / max(totals_b["orders_paid_sum"], 1), 2)

    metric_keys = ["revenue_gross_sum", "revenue_net_sum", "orders_paid_sum", "orders_created_sum"]
    delta: dict[str, dict[str, float | None]] = {}
    for key in metric_keys:
        delta_abs = round(float(totals_a[key] - totals_b[key]), 2)
        delta[key] = {
            "delta_abs": delta_abs,
            "delta_pct": _safe_pct(delta_abs, float(totals_b[key])),
        }

    data = {
        "window_a": {"start": a_start.isoformat(), "end": a_end.isoformat()},
        "window_b": {"start": b_start.isoformat(), "end": b_end.isoformat()},
        "totals_a": totals_a,
        "totals_b": totals_b,
        "delta": delta,
        "aov_a": aov_a,
        "aov_b": aov_b,
    }
    provenance = ToolProvenance(
        sources=[
            f"ownerbot_demo_kpi_daily:{a_start.isoformat()}..{a_end.isoformat()}",
            f"ownerbot_demo_kpi_daily:{b_start.isoformat()}..{b_end.isoformat()}",
            "local_demo",
        ],
        window={
            "scope": "comparison",
            "type": "rolling",
            "window_a": {"start": a_start.isoformat(), "end": a_end.isoformat()},
            "window_b": {"start": b_start.isoformat(), "end": b_end.isoformat()},
            "preset": payload.preset,
        },
        filters_hash=f"preset:{payload.preset};days:{payload.days or ''}",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance, warnings=warnings)
