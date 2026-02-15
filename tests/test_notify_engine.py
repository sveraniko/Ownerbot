from datetime import datetime, timezone

from app.notify.engine import (
    extract_fx_last_apply,
    make_fx_apply_event_key,
    make_ops_event_key,
    should_send_digest,
    should_send_fx_apply_event,
    should_send_fx_delta,
    should_send_ops_alert,
    should_send_weekly,
    alert_triggered,
)


def test_should_send_fx_delta_threshold_and_cooldown() -> None:
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert should_send_fx_delta(now, 1.00, 1.01, 0.5, None, 6) is True
    assert should_send_fx_delta(now, 1.00, 1.003, 0.5, None, 6) is False
    assert should_send_fx_delta(now, 1.00, 1.02, 0.5, datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc), 6) is False


def test_should_send_digest_once_per_calendar_day() -> None:
    now = datetime(2025, 1, 2, 9, 5)
    assert should_send_digest(now, None, "09:00") is True
    assert should_send_digest(now, datetime(2025, 1, 2, 8, 0), "09:00") is False
    assert should_send_digest(now, datetime(2025, 1, 1, 9, 0), "09:00") is True
    assert should_send_digest(datetime(2025, 1, 2, 8, 0), None, "09:00") is False


def test_should_send_weekly_semantics() -> None:
    now = datetime(2025, 1, 13, 10, 0)  # Monday
    assert should_send_weekly(now, None, weekly_day_of_week=0, weekly_time_local="09:30") is True
    assert should_send_weekly(now, datetime(2025, 1, 13, 9, 35), weekly_day_of_week=0, weekly_time_local="09:30") is False
    assert should_send_weekly(now, datetime(2025, 1, 6, 10, 0), weekly_day_of_week=0, weekly_time_local="09:30") is True
    assert should_send_weekly(datetime(2025, 1, 13, 9, 0), None, weekly_day_of_week=0, weekly_time_local="09:30") is False


def test_extract_fx_last_apply_handles_missing_payload() -> None:
    parsed, warning = extract_fx_last_apply({"latest_rate": 1.2})
    assert parsed is None
    assert warning == "missing_last_apply"


def test_make_fx_apply_event_key_is_stable() -> None:
    payload = {
        "at": datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc),
        "result": "applied",
        "affected_count": 12,
        "rate": "1.1200",
        "reason": "threshold",
    }
    assert make_fx_apply_event_key(payload) == make_fx_apply_event_key(dict(payload))


def test_should_send_fx_apply_event_dedupe_and_cooldown() -> None:
    now = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
    event_key = "e1"
    assert should_send_fx_apply_event(now, None, 6, None, event_key) is True
    assert should_send_fx_apply_event(now, None, 6, "e1", event_key) is False
    assert should_send_fx_apply_event(now, datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc), 6, None, event_key) is False


def test_ops_alert_triggered_and_key() -> None:
    snapshot = {
        "unanswered_chats": {"count": 2, "top": [{"thread_id": "t-1"}], "threshold_hours": 2},
        "stuck_orders": {"count": 1, "top": [{"order_id": "o-1"}]},
        "payment_issues": {"count": 0, "top": []},
        "errors": {"count": 1, "top": [{"id": 55}], "window_hours": 24},
        "inventory": {"out_of_stock": 1, "low_stock": 4, "top_out": [{"product_id": "p-1"}], "top_low": [{"product_id": "p-2"}]},
    }
    rules = {
        "ops_unanswered_enabled": True,
        "ops_unanswered_threshold_hours": 2,
        "ops_unanswered_min_count": 1,
        "ops_stuck_orders_enabled": True,
        "ops_stuck_orders_min_count": 1,
        "ops_payment_issues_enabled": True,
        "ops_payment_issues_min_count": 1,
        "ops_errors_enabled": True,
        "ops_errors_window_hours": 24,
        "ops_errors_min_count": 1,
        "ops_out_of_stock_enabled": True,
        "ops_out_of_stock_min_count": 1,
        "ops_low_stock_enabled": True,
        "ops_low_stock_lte": 5,
        "ops_low_stock_min_count": 3,
    }
    triggered, reasons = alert_triggered(snapshot, rules)
    assert triggered is True
    assert reasons

    key1 = make_ops_event_key(snapshot, rules)
    changed = dict(snapshot)
    changed["stuck_orders"] = {"count": 1, "top": [{"order_id": "o-2"}]}
    key2 = make_ops_event_key(changed, rules)
    assert key1 != key2


def test_should_send_ops_alert_dedupe_and_cooldown() -> None:
    now = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
    assert should_send_ops_alert(now, None, 6, None, "k") is True
    assert should_send_ops_alert(now, None, 6, "k", "k") is False
    assert should_send_ops_alert(now, datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc), 6, None, "k2") is False
