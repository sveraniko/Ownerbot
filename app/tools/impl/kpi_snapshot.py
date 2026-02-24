from __future__ import annotations

from datetime import date

from pydantic import BaseModel
from sqlalchemy import select

from app.tools.contracts import ToolProvenance, ToolResponse
from app.tools.providers.local_demo import demo_provenance
from app.storage.models import OwnerbotDemoKpiDaily


class KpiSnapshotPayload(BaseModel):
    day: date | None = None


async def handle(payload: KpiSnapshotPayload, correlation_id: str, session) -> ToolResponse:
    if payload.day:
        stmt = select(OwnerbotDemoKpiDaily).where(OwnerbotDemoKpiDaily.day == payload.day)
    else:
        stmt = select(OwnerbotDemoKpiDaily).order_by(OwnerbotDemoKpiDaily.day.desc()).limit(1)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="NOT_FOUND",
            message="No KPI data available.",
        )
    data = {
        "day": row.day.isoformat(),
        "revenue_gross": float(row.revenue_gross),
        "revenue_net": float(row.revenue_net),
        "orders_paid": row.orders_paid,
        "orders_created": row.orders_created,
        "aov": float(row.aov),
    }
    provenance = ToolProvenance(
        sources=[f"ownerbot_demo_kpi_daily:{row.day.isoformat()}", "local_demo"],
        window={"scope": "day", "type": "snapshot", "day": row.day.isoformat()},
        filters_hash="demo",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
