import pytest

from app.templates.catalog.parsers import (
    parse_ids,
    parse_json_or_kv,
    parse_percent_1_95,
    parse_stock_1_9999,
)


def test_parse_ids_split_and_max() -> None:
    assert parse_ids("a, b\nc") == ["a", "b", "c"]
    with pytest.raises(ValueError):
        parse_ids(" ")
    with pytest.raises(ValueError):
        parse_ids(" ".join([f"id{i}" for i in range(201)]))


def test_parse_percent_and_stock_ranges() -> None:
    assert parse_percent_1_95("95") == 95
    assert parse_stock_1_9999("9999") == 9999

    with pytest.raises(ValueError):
        parse_percent_1_95("0")
    with pytest.raises(ValueError):
        parse_stock_1_9999("10000")


def test_parse_json_or_kv() -> None:
    assert parse_json_or_kv('{"a": 1, "b": true}') == {"a": 1, "b": True}
    assert parse_json_or_kv("x=1,y=true,z=2.5") == {"x": 1, "y": True, "z": 2.5}
    with pytest.raises(ValueError):
        parse_json_or_kv("invalid")
