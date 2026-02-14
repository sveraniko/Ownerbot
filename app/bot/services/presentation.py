from __future__ import annotations

from aiogram.types import BufferedInputFile, Message

from app.bot.services.tool_runner import run_tool
from app.reports.charts import render_revenue_trend_png
from app.reports.pdf_weekly import build_weekly_report_pdf
from app.tools.contracts import ToolActor, ToolTenant


def build_trend_caption(response_data: dict, currency: str) -> str:
    totals = response_data.get("totals", {})
    delta = response_data.get("delta_vs_prev_window") or {}
    total_revenue = float(totals.get("revenue_gross", 0.0))
    delta_pct = delta.get("revenue_gross_pct")
    delta_text = f"{delta_pct}%" if delta_pct is not None else "n/a"
    generated_at = response_data.get("end_day", "n/a")
    return (
        f"Total revenue: {total_revenue:.2f} {currency}\n"
        f"Delta vs prev window: {delta_text}\n"
        f"Currency: {currency}\n"
        f"generated_at: {generated_at}"
    )


async def send_revenue_trend_png(*, message: Message, trend_response: dict, days: int, title: str, currency: str, timezone: str, source_tag: str | None = None) -> None:
    png_bytes = render_revenue_trend_png(
        series=trend_response.get("series", []),
        currency=currency,
        title=title,
        tz=timezone,
    )
    await message.answer_photo(
        BufferedInputFile(png_bytes, filename=f"revenue_trend_{days}d.png"),
        caption=f"Источник: {source_tag or 'DEMO'}\n" + build_trend_caption(trend_response, currency),
    )


async def send_weekly_pdf(*, message: Message, actor: ToolActor, tenant: ToolTenant, correlation_id: str, registry) -> None:
    trend_response = await run_tool(
        "revenue_trend",
        {"days": 30},
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )
    kpi_response = await run_tool(
        "kpi_snapshot",
        {},
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )
    stuck_response = await run_tool(
        "orders_search",
        {"status": "stuck", "limit": 20},
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )
    chats_response = await run_tool(
        "chats_unanswered",
        {"threshold_hours": 0, "limit": 20},
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )

    if any(resp.status == "error" for resp in [trend_response, kpi_response, stuck_response, chats_response]):
        await message.answer("Не удалось собрать weekly PDF: один из tools вернул ошибку.")
        return

    pdf_bytes = build_weekly_report_pdf(
        {
            "correlation_id": correlation_id,
            "currency": tenant.currency,
            "kpi": kpi_response.data,
            "trend": trend_response.data,
            "stuck_orders": stuck_response.data,
            "unanswered_chats": chats_response.data,
        }
    )
    await message.answer_document(
        BufferedInputFile(pdf_bytes, filename="weekly_report.pdf"),
        caption="Weekly PDF report",
    )
