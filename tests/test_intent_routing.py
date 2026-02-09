from app.bot.routers.owner_console import intent_from_text


def test_flag_order_has_priority_over_order_detail() -> None:
    tool_name, payload = intent_from_text("флагни заказ OB-1003 причина тест")

    assert tool_name == "flag_order"
    assert payload["order_id"] == "OB-1003"
    assert payload["reason"] == "тест"
