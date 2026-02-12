from __future__ import annotations

from datetime import date, timedelta

from app.core.settings import Settings
from app.tools.contracts import ToolResponse
from app.upstream.sis_client import SisClient


def upstream_unavailable(correlation_id: str) -> ToolResponse:
    return ToolResponse.error(
        correlation_id=correlation_id,
        code="UPSTREAM_UNAVAILABLE",
        message="SIS upstream is unavailable.",
    )


def _calc_range(days: int) -> tuple[str, str]:
    end_day = date.today()
    start_day = end_day - timedelta(days=days - 1)
    return start_day.isoformat(), end_day.isoformat()


async def run_sis_tool(*, tool_name: str, payload: dict, correlation_id: str, settings: Settings) -> ToolResponse:
    client = SisClient(settings)
    if tool_name == "kpi_snapshot":
        day = payload.get("day")
        return await client.kpi_summary(from_date=day, to_date=day, tz="Europe/Berlin", correlation_id=correlation_id)
    if tool_name == "revenue_trend":
        days = int(payload.get("days", 14))
        from_date, to_date = _calc_range(days)
        return await client.revenue_trend(from_date=from_date, to_date=to_date, tz="Europe/Berlin", correlation_id=correlation_id)
    if tool_name == "orders_search":
        q = payload.get("status") or payload.get("q")
        limit = payload.get("limit", 5)
        return await client.orders_search(q=q, limit=limit, correlation_id=correlation_id)
    if tool_name == "order_detail":
        order_id = str(payload.get("order_id", "")).strip()
        return await client.order_detail(order_id=order_id, correlation_id=correlation_id)
    return ToolResponse.error(correlation_id=correlation_id, code="NOT_IMPLEMENTED", message=f"SIS mapping for {tool_name} not implemented.")
