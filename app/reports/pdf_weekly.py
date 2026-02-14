from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _line(c: canvas.Canvas, text: str, y: float, *, x: float = 20 * mm, font: str = "Helvetica", size: int = 10) -> float:
    if y < 20 * mm:
        c.showPage()
        y = A4[1] - 20 * mm
    c.setFont(font, size)
    c.drawString(x, y, text)
    return y - 6 * mm


def build_weekly_report_pdf(payload: dict[str, Any]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = A4[1] - 20 * mm

    generated_at = payload.get("generated_at") or datetime.utcnow().isoformat()
    correlation_id = payload.get("correlation_id", "n/a")
    currency = payload.get("currency", "EUR")
    kpi = payload.get("kpi") or {}
    trend = payload.get("trend") or {}
    stuck_raw = payload.get("stuck_orders") or {}
    chats_raw = payload.get("unanswered_chats") or {}
    stuck_orders = stuck_raw.get("orders", []) if isinstance(stuck_raw, dict) else stuck_raw
    unanswered_chats = chats_raw.get("threads", []) if isinstance(chats_raw, dict) else chats_raw

    y = _line(c, "OwnerBot Weekly Report", y, font="Helvetica-Bold", size=14)
    y = _line(c, f"Generated at: {generated_at}", y)

    series = trend.get("series", [])
    start_day = series[0].get("day") if series else "n/a"
    end_day = series[-1].get("day") if series else "n/a"
    y = _line(c, f"Period: {start_day} .. {end_day}", y)
    y -= 1 * mm

    y = _line(c, "KPI", y, font="Helvetica-Bold", size=12)
    y = _line(c, f"Revenue gross: {kpi.get('revenue_gross', 'n/a')} {currency}", y)
    y = _line(c, f"Orders paid: {kpi.get('orders_paid', 'n/a')}", y)
    y = _line(c, f"AOV: {kpi.get('aov', 'n/a')} {currency}", y)

    totals = trend.get("totals") or {}
    delta = trend.get("delta_vs_prev_window") or {}
    y -= 1 * mm
    y = _line(c, "Trend summary", y, font="Helvetica-Bold", size=12)
    y = _line(c, f"Revenue (window): {totals.get('revenue_gross', 'n/a')} {currency}", y)
    y = _line(c, f"Delta vs prev window: {delta.get('revenue_gross_pct', 'n/a')}%", y)

    y -= 1 * mm
    y = _line(c, "Operational counters", y, font="Helvetica-Bold", size=12)
    y = _line(c, f"Stuck orders: {len(stuck_orders)}", y)
    y = _line(c, f"Unanswered chats: {len(unanswered_chats)}", y)

    if stuck_orders or unanswered_chats:
        y -= 1 * mm
        y = _line(c, "Details", y, font="Helvetica-Bold", size=12)

    for item in stuck_orders[:10]:
        if isinstance(item, dict):
            line = f"- order {item.get('order_id')} | {item.get('status')} | {item.get('amount')} {item.get('currency')}"
        else:
            line = f"- {item}"
        y = _line(c, line, y)

    for item in unanswered_chats[:10]:
        if isinstance(item, dict):
            line = f"- chat {item.get('thread_id')} | customer={item.get('customer_id')} | last={item.get('last_customer_message_at')}"
        else:
            line = f"- {item}"
        y = _line(c, line, y)

    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 12 * mm, f"correlation_id: {correlation_id}")
    c.save()
    return buf.getvalue()
