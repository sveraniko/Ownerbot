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
    result = route_intent("покажи последние 7 дней выручка")

    assert result.tool == "revenue_trend"
    assert result.payload["days"] == 7


def test_order_detail_match() -> None:
    result = route_intent("заказ ob-7777")

    assert result.tool == "order_detail"
    assert result.payload["order_id"] == "OB-7777"
