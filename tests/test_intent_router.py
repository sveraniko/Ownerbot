from app.bot.services.intent_router import route_intent


def test_notify_precedence_over_other_matches() -> None:
    result = route_intent("/notify заказ OB-1003 завис")

    assert result.tool == "notify_team"
    assert result.payload["message"] == "заказ OB-1003 завис"
    assert result.payload["dry_run"] is True


def test_flag_precedence_over_order_detail() -> None:
    result = route_intent("флагни заказ OB-1003 причина тест")

    assert result.tool == "flag_order"
    assert result.payload["order_id"] == "OB-1003"
    assert result.payload["reason"] == "тест"


def test_revenue_trend_days_extraction() -> None:
    result = route_intent("покажи график выручки 7 дней")

    assert result.tool == "revenue_trend"
    assert result.payload["days"] == 7
    assert result.presentation == {"kind": "chart_png", "days": 7}


def test_trend_command_default_days() -> None:
    result = route_intent("/trend")

    assert result.tool == "revenue_trend"
    assert result.payload["days"] == 14
    assert result.presentation == {"kind": "chart_png", "days": 14}


def test_weekly_pdf_command() -> None:
    result = route_intent("/weekly_pdf")

    assert result.tool == "kpi_snapshot"
    assert result.presentation == {"kind": "weekly_pdf"}


def test_order_detail_match() -> None:
    result = route_intent("заказ ob-7777")

    assert result.tool == "order_detail"
    assert result.payload["order_id"] == "OB-7777"



def test_fx_status_intent() -> None:
    result = route_intent("курс валют")

    assert result.tool == "sis_fx_status"


def test_fx_reprice_auto_intent() -> None:
    result = route_intent("обнови цены")

    assert result.tool == "sis_fx_reprice_auto"
    assert result.payload["dry_run"] is True
    assert result.payload["force"] is False


def test_fx_reprice_auto_force_intent() -> None:
    result = route_intent("обнови цены принудительно")

    assert result.tool == "sis_fx_reprice_auto"
    assert result.payload["force"] is True


def test_demand_forecast_intent_phrases() -> None:
    result = route_intent("прогноз спроса")

    assert result.tool == "demand_forecast"
    assert result.payload["horizon_days"] == 7


def test_reorder_plan_intent_phrases() -> None:
    result = route_intent("что докупить")

    assert result.tool == "reorder_plan"
    assert result.payload == {"lead_time_days": 14, "safety_stock_days": 7, "horizon_days": 14}


def test_business_dashboard_daily_intent() -> None:
    result = route_intent("дай дашборд")

    assert result.tool == "biz_dashboard_daily"
    assert result.payload == {"format": "png"}


def test_business_dashboard_weekly_intent() -> None:
    result = route_intent("еженедельный отчет")

    assert result.tool == "biz_dashboard_weekly"
    assert result.payload == {"format": "pdf"}


def test_business_dashboard_ops_intent() -> None:
    result = route_intent("операционный отчет")

    assert result.tool == "biz_dashboard_ops"
    assert result.payload == {"format": "pdf", "tz": "Europe/Berlin"}


def test_quiet_digest_intents() -> None:
    assert route_intent("тихий дайджест включи").tool == "ntf_quiet_digest_on"
    assert route_intent("тихий дайджест выключи").tool == "ntf_quiet_digest_off"
    assert route_intent("настрой тихий дайджест").tool == "ntf_quiet_digest_rules_set"


def test_escalation_intents() -> None:
    assert route_intent("принято").tool == "ntf_escalation_ack"
    assert route_intent("пауза 12").tool == "ntf_escalation_snooze"
    assert route_intent("пауза 24").payload == {"hours": 24}
    assert route_intent("эскалацию включи").tool == "ntf_escalation_enable"
    assert route_intent("эскалацию выключи").tool == "ntf_escalation_disable"


def test_phrase_pack_source_for_coupon() -> None:
    result = route_intent("купон 15% на 48 часов")

    assert result.tool == "create_coupon"
    assert result.source == "RULE_PHRASE_PACK"
    assert result.payload["percent_off"] == 15
    assert result.payload["hours_valid"] == 48
