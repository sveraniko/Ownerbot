from app.agent_actions.phrase_pack import match_action_phrase


def test_phrase_pack_coupon_extracts_percent_and_hours() -> None:
    result = match_action_phrase("купон -10% на сутки")

    assert result is not None
    assert result.tool_name == "create_coupon"
    assert result.payload_partial["percent_off"] == 10
    assert result.payload_partial["hours_valid"] == 24


def test_phrase_pack_prices_bump_extracts_negative_percent() -> None:
    result = match_action_phrase("снизь цены на 3%")

    assert result is not None
    assert result.tool_name == "sis_prices_bump"
    assert result.payload_partial["value"] == -3


def test_phrase_pack_catalog_extracts_ids_and_target() -> None:
    result = match_action_phrase("скрой товары 44")

    assert result is not None
    assert result.tool_name == "sis_products_publish"
    assert result.payload_partial["target_status"] == "ARCHIVED"
    assert result.payload_partial["product_ids"] == ["44"]
