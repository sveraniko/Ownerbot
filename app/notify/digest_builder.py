from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.notify import extract_fx_rate_and_schedule
from app.tools.impl import (
    chats_unanswered,
    inventory_status,
    kpi_compare,
    orders_search,
    revenue_trend,
    sis_fx_status,
    sys_last_errors,
    top_products,
)


@dataclass
class DigestBundle:
    text: str
    kpi_summary: dict[str, object]
    series: list[dict[str, object]]
    ops_summary: dict[str, object]
    fx_summary: dict[str, object]
    warnings: list[str]


async def build_daily_digest(owner_id: int, session, correlation_id: str, ops_snapshot: dict[str, object] | None = None) -> DigestBundle:
    warnings: list[str] = []

    kpi_res = await kpi_compare.handle(kpi_compare.Payload(preset="wow"), correlation_id=f"{correlation_id}-kpi", session=session)
    trend_res = await revenue_trend.handle(revenue_trend.Payload(days=14), correlation_id=f"{correlation_id}-trend", session=session)
    chats_res = None
    errors_res = None
    orders_res = None
    inventory_res = None
    if ops_snapshot is None:
        chats_res = await chats_unanswered.handle(chats_unanswered.Payload(threshold_hours=2, limit=5), correlation_id=f"{correlation_id}-chat", session=session)
        errors_res = await sys_last_errors.handle(sys_last_errors.Payload(limit=5), correlation_id=f"{correlation_id}-err", session=session)
        orders_res = await orders_search.handle(orders_search.OrdersSearchPayload(preset="stuck", limit=1), correlation_id=f"{correlation_id}-stuck", session=session)
        inventory_res = await inventory_status.handle(inventory_status.Payload(section="all", limit=1), correlation_id=f"{correlation_id}-inv", session=session)
    fx_res = await sis_fx_status.handle(sis_fx_status.Payload(), correlation_id=f"{correlation_id}-fx", session=session)

    for name, res in (("kpi_compare", kpi_res), ("revenue_trend", trend_res), ("sis_fx_status", fx_res)):
        if res.status != "ok":
            warnings.append(f"{name}: unavailable")
    if ops_snapshot is None:
        for name, res in (("chats_unanswered", chats_res), ("sys_last_errors", errors_res), ("orders_search", orders_res), ("inventory_status", inventory_res)):
            if res is not None and res.status != "ok":
                warnings.append(f"{name}: unavailable")
    else:
        warnings.extend([str(w) for w in (ops_snapshot.get("warnings") or [])])

    stuck_count = 0
    low_stock_count = 0
    out_of_stock_count = 0
    unanswered_count = 0
    errors_count = 0
    if ops_snapshot is None:
        if orders_res is not None and orders_res.status == "ok":
            stuck_count = int(orders_res.data.get("count") or 0)
        if inventory_res is not None and inventory_res.status == "ok":
            counts = inventory_res.data.get("counts") or {}
            low_stock_count = int(counts.get("low_stock") or 0)
            out_of_stock_count = int(counts.get("out_of_stock") or 0)
        if chats_res is not None and chats_res.status == "ok":
            unanswered_count = int(chats_res.data.get("count") or 0)
        if errors_res is not None and errors_res.status == "ok":
            errors_count = int(errors_res.data.get("count") or 0)
    else:
        unanswered_count = int((ops_snapshot.get("unanswered_chats") or {}).get("count") or 0)
        stuck_count = int((ops_snapshot.get("stuck_orders") or {}).get("count") or 0)
        errors_count = int((ops_snapshot.get("errors") or {}).get("count") or 0)
        low_stock_count = int((ops_snapshot.get("inventory") or {}).get("low_stock") or 0)
        out_of_stock_count = int((ops_snapshot.get("inventory") or {}).get("out_of_stock") or 0)

    kpi_summary: dict[str, object] = {}
    if kpi_res.status == "ok":
        totals_a = kpi_res.data.get("totals_a") or {}
        delta = (kpi_res.data.get("delta") or {}).get("revenue_net_sum") or {}
        orders_delta = (kpi_res.data.get("delta") or {}).get("orders_paid_sum") or {}
        kpi_summary = {
            "revenue_net_sum": float(totals_a.get("revenue_net_sum") or 0),
            "orders_paid_sum": int(totals_a.get("orders_paid_sum") or 0),
            "aov": float(kpi_res.data.get("aov_a") or 0),
            "revenue_net_wow_pct": delta.get("delta_pct"),
            "orders_paid_wow_pct": orders_delta.get("delta_pct"),
        }

    series = trend_res.data.get("series", []) if trend_res.status == "ok" else []

    ops_summary = {
        "unanswered_chats_2h": unanswered_count,
        "stuck_orders": stuck_count,
        "last_errors_count": errors_count,
        "low_stock": low_stock_count,
        "out_of_stock": out_of_stock_count,
    }

    fx_summary: dict[str, object] = {"rate": None, "would_apply": None, "last_apply_result": None}
    if fx_res.status == "ok":
        snap = extract_fx_rate_and_schedule(fx_res.data)
        fx_summary = {
            "rate": snap.effective_rate,
            "would_apply": fx_res.data.get("would_apply"),
            "last_apply_result": snap.schedule_fields.get("last_apply_result"),
        }

    wow_revenue = _fmt_pct(kpi_summary.get("revenue_net_wow_pct"))
    wow_orders = _fmt_pct(kpi_summary.get("orders_paid_wow_pct"))
    fx_rate = fx_summary.get("rate")
    fx_line = f"💱 FX: {float(fx_rate):.4f} (would_apply={fx_summary.get('would_apply')})" if isinstance(fx_rate, (int, float)) else "💱 FX: N/A"

    text = (
        f"🗓 Daily digest {date.today().isoformat()}\n"
        f"💰 Revenue net: {kpi_summary.get('revenue_net_sum', 0):.2f} (WoW {wow_revenue})\n"
        f"🧾 Paid orders: {kpi_summary.get('orders_paid_sum', 0)} (WoW {wow_orders}), AOV: {kpi_summary.get('aov', 0):.2f}\n"
        f"💬 Unanswered chats >2h: {ops_summary['unanswered_chats_2h']}\n"
        f"📦 Stuck orders: {ops_summary['stuck_orders']} | low stock: {ops_summary['low_stock']} | OOS: {ops_summary['out_of_stock']}\n"
        f"⚠️ Errors last 24h: {ops_summary['last_errors_count']}\n"
        f"{fx_line}"
    )
    if warnings:
        text += "\n⚠️ " + "; ".join(warnings[:3])

    return DigestBundle(text=text, kpi_summary=kpi_summary, series=series, ops_summary=ops_summary, fx_summary=fx_summary, warnings=warnings)


async def build_weekly_digest(owner_id: int, session, correlation_id: str) -> DigestBundle:
    del owner_id
    warnings: list[str] = []
    kpi_res = await kpi_compare.handle(kpi_compare.Payload(preset="wow", days=7), correlation_id=f"{correlation_id}-kpi", session=session)
    trend_res = await revenue_trend.handle(revenue_trend.Payload(days=30), correlation_id=f"{correlation_id}-trend", session=session)
    chats_res = await chats_unanswered.handle(chats_unanswered.Payload(threshold_hours=2, limit=5), correlation_id=f"{correlation_id}-chat", session=session)
    errors_res = await sys_last_errors.handle(sys_last_errors.Payload(limit=5), correlation_id=f"{correlation_id}-err", session=session)
    stuck_res = await orders_search.handle(orders_search.OrdersSearchPayload(preset="stuck", limit=1), correlation_id=f"{correlation_id}-stuck", session=session)
    top_res = await top_products.handle(top_products.Payload(limit=5, metric="revenue", direction="top", group_by="product", days=7), correlation_id=f"{correlation_id}-top", session=session)

    for name, res in (("kpi_compare", kpi_res), ("revenue_trend", trend_res), ("chats_unanswered", chats_res), ("sys_last_errors", errors_res), ("orders_search", stuck_res), ("top_products", top_res)):
        if res.status != "ok":
            warnings.append(f"{name}: unavailable")

    kpi_summary = {}
    if kpi_res.status == "ok":
        totals = kpi_res.data.get("totals_a") or {}
        deltas = kpi_res.data.get("delta") or {}
        kpi_summary = {
            "revenue_net_sum": float(totals.get("revenue_net_sum") or 0),
            "orders_paid_sum": int(totals.get("orders_paid_sum") or 0),
            "aov": float(kpi_res.data.get("aov_a") or 0),
            "revenue_net_wow_pct": (deltas.get("revenue_net_sum") or {}).get("delta_pct"),
            "orders_paid_wow_pct": (deltas.get("orders_paid_sum") or {}).get("delta_pct"),
            "window_a": kpi_res.data.get("window_a") or {},
        }

    ops_summary = {
        "unanswered_chats_2h": int((chats_res.data if chats_res.status == "ok" else {}).get("count") or 0),
        "stuck_orders": int((stuck_res.data if stuck_res.status == "ok" else {}).get("count") or 0),
        "last_errors_count": int((errors_res.data if errors_res.status == "ok" else {}).get("count") or 0),
    }
    top_rows = (top_res.data if top_res.status == "ok" else {}).get("rows") or []
    if top_rows:
        ops_summary["top_products"] = [row.get("title") for row in top_rows[:5]]

    series = trend_res.data.get("series", []) if trend_res.status == "ok" else []
    window_a = kpi_summary.get("window_a") or {}
    text = (
        f"📅 Weekly report ({window_a.get('start', 'n/a')}..{window_a.get('end', 'n/a')})\n"
        f"Revenue net: {kpi_summary.get('revenue_net_sum', 0):.2f} ({_fmt_pct(kpi_summary.get('revenue_net_wow_pct'))} vs prev week)\n"
        f"Orders paid: {kpi_summary.get('orders_paid_sum', 0)} ({_fmt_pct(kpi_summary.get('orders_paid_wow_pct'))}), AOV: {kpi_summary.get('aov', 0):.2f}\n"
        f"Top issues: chats>2h={ops_summary['unanswered_chats_2h']}, stuck={ops_summary['stuck_orders']}, errors={ops_summary['last_errors_count']}"
    )
    if warnings:
        text += "\n⚠️ " + "; ".join(warnings[:3])

    return DigestBundle(text=text, kpi_summary=kpi_summary, series=series, ops_summary=ops_summary, fx_summary={}, warnings=warnings)


def _fmt_pct(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):+.2f}%"
    return "N/A"
