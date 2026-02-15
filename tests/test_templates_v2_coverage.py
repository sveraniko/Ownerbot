from app.templates.catalog.loader import load_template_catalog


EXPECTED_TEMPLATE_IDS = {
    "RPT_KPI_TODAY",
    "RPT_KPI_YESTERDAY",
    "RPT_KPI_7D",
    "RPT_KPI_30D",
    "RPT_COMPARE_WOW",
    "RPT_COMPARE_MOM",
    "RPT_COMPARE_CUSTOM",
    "RPT_REVENUE_TREND_30D",
    "RPT_REVENUE_TREND_30D_PNG",
    "RPT_REVENUE_TREND_90D_PNG",
    "RPT_STUCK_ORDERS_SUMMARY",
    "RPT_UNANSWERED_CHATS_SUMMARY",
    "RPT_WEEKLY_PDF",
    "RPT_TOP_PRODUCTS_7D",
    "RPT_TOP_PRODUCTS_QTY_7D",
    "RPT_BOTTOM_PRODUCTS_7D",
    "RPT_TOP_CATEGORIES_30D",
    "BIZ_DASHBOARD_DAILY_PNG",
    "BIZ_DASHBOARD_DAILY_TEXT",
    "BIZ_DASHBOARD_WEEKLY_PDF",
    "BIZ_OPS_DASHBOARD_PDF",
    "ORD_FIND_BY_ID",
    "ORD_FIND_BY_PHONE",
    "ORD_FIND_BY_STATUS",
    "ORD_FIND_RECENT",
    "ORD_STUCK_LIST",
    "ORD_LATE_SHIP",
    "ORD_PAYMENT_ISSUES",
    "ORD_FLAG",
    "ORD_NOTIFY_TEAM",
    "ORD_BULK_FLAG",
    "TEAM_UNANSWERED_2H",
    "TEAM_UNANSWERED_6H",
    "TEAM_QUEUE_SUMMARY",
    "TEAM_PING_MANAGER",
    "TEAM_BROADCAST",
    "SYS_HEALTH",
    "SYS_LAST_ERRORS",
    "SYS_UPSTREAM_MODE",
    "SYS_AUDIT_RECENT",
    "SYS_ONBOARD_TEST_RUN",
    "SYS_ONBOARD_APPLY_MINIMAL",
    "SYS_ONBOARD_APPLY_STANDARD",
    "SYS_ONBOARD_STATUS",
    "ADV_RAW_TOOL_CALL",
    "ADV_EXPORT_JSON",
    "ADV_REPLAY_LAST",
    "PRD_INVENTORY_STATUS",
    "PRD_NO_PHOTO",
    "PRD_NO_VIDEO",
    "PRD_NO_PRICE",
    "PRD_LOW_STOCK",
    "PRD_RETURN_FLAGS",
    "PRD_SALES_RANK_30D",
    "PRD_DISABLE",
    "PRD_UPDATE_PRICE",
    "DSC_STATUS",
    "DSC_TOP_USED",
    "DSC_CREATE_COUPON",
    "FRC_7D_DEMAND",
    "FRC_REORDER_PLAN",
    "NTF_STATUS",
    "NTF_FX_DELTA_SUBSCRIBE",
    "NTF_FX_DELTA_UNSUBSCRIBE",
    "NTF_FX_APPLY_EVENTS_SUBSCRIBE",
    "NTF_FX_APPLY_EVENTS_UNSUBSCRIBE",
    "NTF_DAILY_DIGEST_SUBSCRIBE",
    "NTF_DAILY_DIGEST_UNSUBSCRIBE",
    "NTF_SEND_DIGEST_NOW",
    "NTF_OPS_ALERTS_SUBSCRIBE",
    "NTF_OPS_ALERTS_UNSUBSCRIBE",
}


def test_templates_v2_coverage_ids_present() -> None:
    catalog = load_template_catalog()
    ids = {spec.template_id for spec in catalog.templates}
    assert EXPECTED_TEMPLATE_IDS.issubset(ids)


def test_templates_v2_categories_present() -> None:
    catalog = load_template_catalog()
    categories = set(catalog.list_categories())
    assert {"reports", "orders", "team", "systems", "advanced", "products", "forecast", "notifications"}.issubset(categories)
