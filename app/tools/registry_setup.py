from __future__ import annotations

from app.tools.registry import ToolRegistry
from app.tools.impl import (
    kpi_snapshot,
    orders_search,
    revenue_trend,
    funnel_snapshot,
    order_detail,
    chats_unanswered,
    top_products,
    inventory_status,
    refunds_anomalies,
    truststack_signals,
    create_coupon,
    adjust_price,
    coupons_status,
    coupons_top_used,
    notify_team,
    pause_campaign,
    flag_order,
    retrospective_last,
    sis_prices_bump,
    sis_fx_reprice,
    sis_fx_rollback,
    sis_fx_status,
    sis_fx_reprice_auto,
    sis_fx_settings_update,
    sis_products_publish,
    sis_looks_publish,
    sis_discounts_clear,
    sis_discounts_set,
    sys_upstream_mode,
    sys_health,
    sys_audit_recent,
    sys_last_errors,
    kpi_compare,
    team_queue_summary,
    bulk_flag_order,
    demand_forecast,
    reorder_plan,
    ntf_status,
    ntf_fx_delta_subscribe,
    ntf_fx_delta_unsubscribe,
    ntf_daily_digest_subscribe,
    ntf_daily_digest_unsubscribe,
    ntf_send_digest_now,
)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("kpi_snapshot", "1.0", kpi_snapshot.KpiSnapshotPayload, kpi_snapshot.handle)
    registry.register("orders_search", "1.0", orders_search.OrdersSearchPayload, orders_search.handle)
    registry.register("revenue_trend", "1.0", revenue_trend.Payload, revenue_trend.handle)
    registry.register("funnel_snapshot", "1.0", funnel_snapshot.Payload, funnel_snapshot.handle, is_stub=True)
    registry.register("order_detail", "1.0", order_detail.Payload, order_detail.handle)
    registry.register("chats_unanswered", "1.0", chats_unanswered.Payload, chats_unanswered.handle)
    registry.register("top_products", "1.1", top_products.Payload, top_products.handle, is_stub=False)
    registry.register("inventory_status", "1.1", inventory_status.Payload, inventory_status.handle, is_stub=False)
    registry.register("refunds_anomalies", "1.0", refunds_anomalies.Payload, refunds_anomalies.handle, is_stub=True)
    registry.register("truststack_signals", "1.0", truststack_signals.Payload, truststack_signals.handle, is_stub=True)
    registry.register("create_coupon", "1.0", create_coupon.Payload, create_coupon.handle, is_stub=False, kind="action")
    registry.register("adjust_price", "1.0", adjust_price.Payload, adjust_price.handle, is_stub=False, kind="action")
    registry.register("coupons_status", "1.0", coupons_status.Payload, coupons_status.handle, is_stub=False)
    registry.register("coupons_top_used", "1.0", coupons_top_used.Payload, coupons_top_used.handle, is_stub=False)
    registry.register("notify_team", "1.0", notify_team.Payload, notify_team.handle, is_stub=False, kind="action")
    registry.register("pause_campaign", "1.0", pause_campaign.Payload, pause_campaign.handle, is_stub=True, kind="action")
    registry.register("flag_order", "1.0", flag_order.Payload, flag_order.handle, kind="action")
    registry.register("sis_prices_bump", "1.0", sis_prices_bump.Payload, sis_prices_bump.handle, kind="action")
    registry.register("sis_fx_reprice", "1.0", sis_fx_reprice.Payload, sis_fx_reprice.handle, kind="action")
    registry.register("sis_fx_rollback", "1.0", sis_fx_rollback.Payload, sis_fx_rollback.handle, kind="action")
    registry.register("sis_fx_status", "1.0", sis_fx_status.Payload, sis_fx_status.handle)
    registry.register("sis_fx_reprice_auto", "1.0", sis_fx_reprice_auto.Payload, sis_fx_reprice_auto.handle, kind="action")
    registry.register("sis_fx_settings_update", "1.0", sis_fx_settings_update.Payload, sis_fx_settings_update.handle, kind="action")
    registry.register("sis_products_publish", "1.0", sis_products_publish.Payload, sis_products_publish.handle, kind="action")
    registry.register("sis_looks_publish", "1.0", sis_looks_publish.Payload, sis_looks_publish.handle, kind="action")
    registry.register("sis_discounts_clear", "1.0", sis_discounts_clear.Payload, sis_discounts_clear.handle, kind="action")
    registry.register("sis_discounts_set", "1.0", sis_discounts_set.Payload, sis_discounts_set.handle, kind="action")
    registry.register("sys_upstream_mode", "1.0", sys_upstream_mode.Payload, sys_upstream_mode.handle)
    registry.register("sys_health", "1.0", sys_health.Payload, sys_health.handle)
    registry.register("sys_audit_recent", "1.0", sys_audit_recent.Payload, sys_audit_recent.handle)
    registry.register("sys_last_errors", "1.0", sys_last_errors.Payload, sys_last_errors.handle)
    registry.register("kpi_compare", "1.1", kpi_compare.Payload, kpi_compare.handle, is_stub=False)
    registry.register("team_queue_summary", "1.1", team_queue_summary.Payload, team_queue_summary.handle, is_stub=False)
    registry.register("bulk_flag_order", "1.0", bulk_flag_order.Payload, bulk_flag_order.handle, kind="action")
    registry.register("retrospective_last", "1.0", retrospective_last.Payload, retrospective_last.handle)
    registry.register("demand_forecast", "1.0", demand_forecast.Payload, demand_forecast.handle)
    registry.register("reorder_plan", "1.0", reorder_plan.Payload, reorder_plan.handle)
    registry.register("ntf_status", "1.0", ntf_status.Payload, ntf_status.handle)
    registry.register("ntf_fx_delta_subscribe", "1.0", ntf_fx_delta_subscribe.Payload, ntf_fx_delta_subscribe.handle)
    registry.register("ntf_fx_delta_unsubscribe", "1.0", ntf_fx_delta_unsubscribe.Payload, ntf_fx_delta_unsubscribe.handle)
    registry.register("ntf_daily_digest_subscribe", "1.0", ntf_daily_digest_subscribe.Payload, ntf_daily_digest_subscribe.handle)
    registry.register("ntf_daily_digest_unsubscribe", "1.0", ntf_daily_digest_unsubscribe.Payload, ntf_daily_digest_unsubscribe.handle)
    registry.register("ntf_send_digest_now", "1.0", ntf_send_digest_now.Payload, ntf_send_digest_now.handle)
    return registry
