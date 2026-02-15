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


def render_ops_pdf(snapshot: dict, report_title: str = "OwnerBot Ops Report", tz: str = "Europe/Berlin") -> bytes:
    snapshot = snapshot or {}
    unanswered = snapshot.get("unanswered_chats") or {}
    stuck = snapshot.get("stuck_orders") or {}
    payments = snapshot.get("payment_issues") or {}
    errors = snapshot.get("errors") or {}
    inventory = snapshot.get("inventory") or {}
    warnings = snapshot.get("warnings") or []

    generated_at = "n/a"
    correlation_id = None
    meta = snapshot.get("meta") or {}
    if isinstance(meta, dict):
        generated_at = str(meta.get("generated_at") or generated_at)
        correlation_id = meta.get("correlation_id")

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    y = A4[1] - 18 * mm

    y = _line(pdf, report_title, y, size=14, bold=True)
    y = _line(pdf, f"Generated: {generated_at}", y)
    y = _line(pdf, f"Timezone: {tz}", y)
    y -= 1 * mm

    y = _line(pdf, "KPI", y, bold=True)
    y = _line(
        pdf,
        f"Unanswered chats >{int(unanswered.get('threshold_hours') or 0)}h: {int(unanswered.get('count') or 0)}",
        y,
    )
    y = _line(pdf, f"Stuck orders ({str(stuck.get('preset') or 'n/a')}): {int(stuck.get('count') or 0)}", y)
    y = _line(pdf, f"Payment issues ({str(payments.get('preset') or 'n/a')}): {int(payments.get('count') or 0)}", y)
    y = _line(pdf, f"Errors ({int(errors.get('window_hours') or 0)}h): {int(errors.get('count') or 0)}", y)
    y = _line(
        pdf,
        f"Inventory out={int(inventory.get('out_of_stock') or 0)} / low<={int(inventory.get('low_stock_lte') or 0)}: {int(inventory.get('low_stock') or 0)}",
        y,
    )

    y -= 1 * mm
    y = _line(pdf, "Top items", y, bold=True)
    y = _write_top_block(pdf, y, "Unanswered chats", unanswered.get("top") or [], _fmt_chat_item)
    y = _write_top_block(pdf, y, "Stuck orders", stuck.get("top") or [], _fmt_order_item)
    y = _write_top_block(pdf, y, "Payment issues", payments.get("top") or [], _fmt_order_item)
    y = _write_top_block(pdf, y, "Recent errors", errors.get("top") or [], _fmt_error_item)
    y = _write_top_block(pdf, y, "Inventory out of stock", inventory.get("top_out") or [], _fmt_inventory_item)
    y = _write_top_block(pdf, y, "Inventory low stock", inventory.get("top_low") or [], _fmt_inventory_item)

    y -= 1 * mm
    y = _line(pdf, "Action checklist", y, bold=True)
    checklist = _build_ops_checklist(unanswered, stuck, payments, errors, inventory)
    if not checklist:
        checklist = ["No urgent actions from this snapshot."]
    for item in checklist:
        y = _line(pdf, f"- {item}", y)

    y -= 1 * mm
    y = _line(pdf, "Footer", y, bold=True)
    if warnings:
        y = _line(pdf, f"Warnings: {' | '.join(str(w)[:120] for w in warnings[:5])}", y)
    else:
        y = _line(pdf, "Warnings: none", y)
    if correlation_id:
        y = _line(pdf, f"Correlation ID: {str(correlation_id)[:120]}", y)

    pdf.save()
    return buf.getvalue()


def _write_top_block(pdf: canvas.Canvas, y: float, title: str, items: list, formatter) -> float:
    y = _line(pdf, title, y, bold=True)
    if not items:
        return _line(pdf, "- none", y)
    for item in items[:3]:
        y = _line(pdf, f"- {formatter(item)}", y)
    return y


def _fmt_chat_item(item: dict) -> str:
    if not isinstance(item, dict):
        return "n/a"
    thread = str(item.get("thread_id") or item.get("chat_id") or "n/a")
    age = item.get("age_hours")
    message = _trim_text(str(item.get("last_message") or ""), 80)
    age_part = f"{age}h" if age is not None else "n/a"
    return f"thread={thread}, age={age_part}, last='{message}'"


def _fmt_order_item(item: dict) -> str:
    if not isinstance(item, dict):
        return "n/a"
    order_id = str(item.get("order_id") or item.get("id") or "n/a")
    status = str(item.get("status") or "n/a")
    age = item.get("age_hours")
    amount = item.get("amount")
    amount_part = f", amount={amount}" if amount is not None else ""
    age_part = f", age={age}h" if age is not None else ""
    return f"{order_id} ({status}{age_part}{amount_part})"


def _fmt_error_item(item: dict) -> str:
    if not isinstance(item, dict):
        return "n/a"
    cls = str(item.get("error_class") or item.get("class") or "error")
    source = str(item.get("source") or "n/a")
    message = _trim_text(str(item.get("message") or ""), 120)
    return f"{cls}@{source}: {message}"


def _fmt_inventory_item(item: dict) -> str:
    if not isinstance(item, dict):
        return "n/a"
    sku = str(item.get("sku") or "n/a")
    title = _trim_text(str(item.get("title") or item.get("name") or ""), 70)
    qty = item.get("qty")
    return f"{sku} ({title}) qty={qty if qty is not None else 'n/a'}"


def _trim_text(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def _build_ops_checklist(unanswered: dict, stuck: dict, payments: dict, errors: dict, inventory: dict) -> list[str]:
    checklist: list[str] = []
    unanswered_count = int(unanswered.get("count") or 0)
    stuck_count = int(stuck.get("count") or 0)
    payment_count = int(payments.get("count") or 0)
    errors_count = int(errors.get("count") or 0)
    out_of_stock = int(inventory.get("out_of_stock") or 0)
    low_stock = int(inventory.get("low_stock") or 0)
    if unanswered_count > 0:
        checklist.append(f"Reply to {unanswered_count} unanswered chats")
    if stuck_count > 0:
        checklist.append(f"Review {stuck_count} stuck orders")
    if payment_count > 0:
        checklist.append(f"Fix payment issues for {payment_count} orders")
    if errors_count > 0:
        checklist.append(f"Investigate {errors_count} recent errors")
    if out_of_stock > 0 or low_stock > 0:
        checklist.append(f"Reorder inventory (out={out_of_stock}, low={low_stock})")
    return checklist
