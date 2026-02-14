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
