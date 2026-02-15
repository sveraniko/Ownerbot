from __future__ import annotations

from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.notify.digest_builder import DigestBundle


def render_revenue_trend_png(series: list[dict], title: str, subtitle: str) -> bytes:
    days = [str(item.get("day") or item.get("date") or "") for item in series]
    revenue = [float(item.get("revenue_net") or item.get("revenue_gross") or 0) for item in series]

    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    if days:
        ax.plot(days, revenue, color="#2E86C1", linewidth=2.0, marker="o")
    else:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
    ax.set_title(title)
    ax.set_xlabel(subtitle)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate(rotation=25, ha="right")

    out = BytesIO()
    fig.savefig(out, format="png", dpi=140)
    plt.close(fig)
    return out.getvalue()


def render_weekly_pdf(bundle: DigestBundle, report_title: str = "OwnerBot Weekly Report") -> bytes:
    chart = render_revenue_trend_png(bundle.series, "Revenue trend", "weekly context")

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    y = A4[1] - 18 * mm

    y = _line(pdf, report_title, y, size=14, bold=True)
    y = _line(pdf, bundle.text[:280], y)
    y -= 2 * mm

    y = _line(pdf, "KPI", y, bold=True)
    y = _line(pdf, f"Revenue net: {bundle.kpi_summary.get('revenue_net_sum', 'n/a')}", y)
    y = _line(pdf, f"Orders paid: {bundle.kpi_summary.get('orders_paid_sum', 'n/a')}", y)
    y = _line(pdf, f"AOV: {bundle.kpi_summary.get('aov', 'n/a')}", y)

    y -= 2 * mm
    y = _line(pdf, "Top issues", y, bold=True)
    y = _line(pdf, f"Unanswered chats >2h: {bundle.ops_summary.get('unanswered_chats_2h', 0)}", y)
    y = _line(pdf, f"Stuck orders: {bundle.ops_summary.get('stuck_orders', 0)}", y)
    y = _line(pdf, f"Errors: {bundle.ops_summary.get('last_errors_count', 0)}", y)

    if bundle.warnings:
        y -= 2 * mm
        y = _line(pdf, "Warnings", y, bold=True)
        for warning in bundle.warnings[:5]:
            y = _line(pdf, f"- {warning[:120]}", y)

    y -= 3 * mm
    if y < 95 * mm:
        pdf.showPage()
        y = A4[1] - 20 * mm
    pdf.drawImage(ImageReader(BytesIO(chart)), 20 * mm, y - 70 * mm, width=170 * mm, height=65 * mm, preserveAspectRatio=True)

    pdf.save()
    return buf.getvalue()


def _line(pdf: canvas.Canvas, text: str, y: float, size: int = 10, bold: bool = False) -> float:
    if y < 18 * mm:
        pdf.showPage()
        y = A4[1] - 20 * mm
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.drawString(18 * mm, y, text)
    return y - 6 * mm
