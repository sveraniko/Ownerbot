from __future__ import annotations

from typing import Any

from app.tools.impl import chats_unanswered, inventory_status, orders_search, sys_last_errors


async def build_ops_snapshot(session, correlation_id: str, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = rules or {}
    warnings: list[str] = []

    unanswered_threshold = int(rules.get("ops_unanswered_threshold_hours", 2) or 2)
    low_stock_lte = int(rules.get("ops_low_stock_lte", 5) or 5)
    errors_window = int(rules.get("ops_errors_window_hours", 24) or 24)
    stuck_preset = str(rules.get("ops_stuck_orders_preset", "stuck") or "stuck")
    payment_preset = str(rules.get("ops_payment_issues_preset", "payment_issues") or "payment_issues")

    chats_res = await chats_unanswered.handle(
        chats_unanswered.Payload(threshold_hours=unanswered_threshold, limit=3),
        correlation_id=f"{correlation_id}-ops-chats",
        session=session,
    )
    stuck_res = await orders_search.handle(
        orders_search.OrdersSearchPayload(preset=stuck_preset, limit=3),
        correlation_id=f"{correlation_id}-ops-stuck",
        session=session,
    )
    payment_res = await orders_search.handle(
        orders_search.OrdersSearchPayload(preset=payment_preset, limit=3),
        correlation_id=f"{correlation_id}-ops-pay",
        session=session,
    )
    errors_res = await sys_last_errors.handle(
        sys_last_errors.Payload(limit=20),
        correlation_id=f"{correlation_id}-ops-errors",
        session=session,
    )
    inventory_res = await inventory_status.handle(
        inventory_status.Payload(low_stock_lte=low_stock_lte, limit=3, section="all"),
        correlation_id=f"{correlation_id}-ops-inventory",
        session=session,
    )

    for name, res in (
        ("chats_unanswered", chats_res),
        (f"orders_search({stuck_preset})", stuck_res),
        (f"orders_search({payment_preset})", payment_res),
        ("sys_last_errors", errors_res),
        ("inventory_status", inventory_res),
    ):
        if res.status != "ok":
            code = ((res.error.code if res.error else None) or "unknown")
            warnings.append(f"{name}:{code}")

    errors_events = (errors_res.data.get("events") or []) if errors_res.status == "ok" else []
    errors_count_window = 0
    if errors_window >= 24:
        errors_count_window = int(errors_res.data.get("count") or 0) if errors_res.status == "ok" else 0
    else:
        for ev in errors_events:
            occurred_at = str(ev.get("occurred_at") or "")
            # Lightweight heuristic: tool already returns recent-first ordered list.
            if occurred_at:
                errors_count_window += 1

    counts = (inventory_res.data.get("counts") or {}) if inventory_res.status == "ok" else {}
    out_list = (inventory_res.data.get("out_of_stock") or []) if inventory_res.status == "ok" else []
    low_list = (inventory_res.data.get("low_stock") or []) if inventory_res.status == "ok" else []

    return {
        "unanswered_chats": {
            "count": int((chats_res.data if chats_res.status == "ok" else {}).get("count") or 0),
            "top": ((chats_res.data if chats_res.status == "ok" else {}).get("threads") or [])[:3],
            "threshold_hours": unanswered_threshold,
        },
        "stuck_orders": {
            "count": int((stuck_res.data if stuck_res.status == "ok" else {}).get("count") or 0),
            "top": ((stuck_res.data if stuck_res.status == "ok" else {}).get("items") or [])[:3],
            "preset": stuck_preset,
        },
        "payment_issues": {
            "count": int((payment_res.data if payment_res.status == "ok" else {}).get("count") or 0),
            "top": ((payment_res.data if payment_res.status == "ok" else {}).get("items") or [])[:3],
            "preset": payment_preset,
        },
        "errors": {
            "count": errors_count_window,
            "top": errors_events[:3],
            "window_hours": errors_window,
        },
        "inventory": {
            "out_of_stock": int(counts.get("out_of_stock") or 0),
            "low_stock": int(counts.get("low_stock") or 0),
            "top_out": out_list[:3],
            "top_low": low_list[:3],
            "low_stock_lte": low_stock_lte,
        },
        "warnings": warnings,
    }
