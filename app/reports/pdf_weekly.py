from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _line(c: canvas.Canvas, text: str, y: float, *, x: float = 20 * mm, font: str = "Helvetica", size: int = 10) -> float:
    c.setFont(font, size)
    c.drawString(x, y, text)
    return y - 6 * mm


def build_weekly_report_pdf(payload: dict[str, Any]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 20 * mm

    generated_at = payload.get("generated_at") or datetime.utcnow().isoformat()
    correlation_id = payload.get("correlation_id", "n/a")

    y = _line(c, "OwnerBot Weekly Report (DEMO)", y, font="Helvetica-Bold", size=14)
    y = _line(c, f"Generated at: {generated_at}", y)
    y = _line(c, "Mode: DEMO", y)
    y -= 2 * mm

    y = _line(c, "KPI summary", y, font="Helvetica-Bold", size=12)
    for row in payload.get("kpi_summary", []):
        y = _line(c, f"- {row}", y)

    y -= 1 * mm
    y = _line(c, "7-day revenue summary", y, font="Helvetica-Bold", size=12)
    for row in payload.get("revenue_summary", []):
        y = _line(c, f"- {row}", y)

    y -= 1 * mm
    y = _line(c, "Stuck orders", y, font="Helvetica-Bold", size=12)
    stuck_orders = payload.get("stuck_orders", [])
    if stuck_orders:
        for row in stuck_orders:
            y = _line(c, f"- {row}", y)
    else:
        y = _line(c, "- none", y)

    y -= 1 * mm
    y = _line(c, "Unanswered chats", y, font="Helvetica-Bold", size=12)
    unanswered_chats = payload.get("unanswered_chats", [])
    if unanswered_chats:
        for row in unanswered_chats:
            y = _line(c, f"- {row}", y)
    else:
        y = _line(c, "- none", y)

    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 12 * mm, f"correlation_id: {correlation_id}")
    c.save()
    return buf.getvalue()
