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
    notify_team,
    pause_campaign,
    flag_order,
)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("kpi_snapshot", "1.0", kpi_snapshot.KpiSnapshotPayload, kpi_snapshot.handle)
    registry.register("orders_search", "1.0", orders_search.OrdersSearchPayload, orders_search.handle)
    registry.register("revenue_trend", "1.0", revenue_trend.Payload, revenue_trend.handle)
    registry.register("funnel_snapshot", "1.0", funnel_snapshot.Payload, funnel_snapshot.handle, is_stub=True)
    registry.register("order_detail", "1.0", order_detail.Payload, order_detail.handle)
    registry.register("chats_unanswered", "1.0", chats_unanswered.Payload, chats_unanswered.handle)
    registry.register("top_products", "1.0", top_products.Payload, top_products.handle, is_stub=True)
    registry.register("inventory_status", "1.0", inventory_status.Payload, inventory_status.handle, is_stub=True)
    registry.register("refunds_anomalies", "1.0", refunds_anomalies.Payload, refunds_anomalies.handle, is_stub=True)
    registry.register("truststack_signals", "1.0", truststack_signals.Payload, truststack_signals.handle, is_stub=True)
    registry.register("create_coupon", "1.0", create_coupon.Payload, create_coupon.handle, is_stub=True)
    registry.register("adjust_price", "1.0", adjust_price.Payload, adjust_price.handle, is_stub=True)
    registry.register("notify_team", "1.0", notify_team.Payload, notify_team.handle, is_stub=True)
    registry.register("pause_campaign", "1.0", pause_campaign.Payload, pause_campaign.handle, is_stub=True)
    registry.register("flag_order", "1.0", flag_order.Payload, flag_order.handle, is_stub=True)
    return registry
