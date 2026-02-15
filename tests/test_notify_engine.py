from datetime import datetime, timezone

from app.notify.engine import (
    extract_fx_last_apply,
    make_fx_apply_event_key,
    should_send_digest,
    should_send_fx_apply_event,
    should_send_fx_delta,
    should_send_weekly,
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
