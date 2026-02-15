from datetime import datetime, timezone
from types import SimpleNamespace

from app.notify.engine import (
    extract_fx_last_apply,
    make_fx_apply_event_key,
    make_ops_event_key,
    should_send_digest,
    parse_pct_safe,
    quiet_digest_triggered,
    should_attempt_digest_quiet,
    should_force_heartbeat,
    should_send_fx_apply_event,
    should_send_fx_delta,
    should_send_ops_alert,
    should_send_weekly,
    alert_triggered,
    build_critical_snapshot,
    make_critical_event_key,
    should_send_escalation,
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


def test_parse_pct_safe_variants() -> None:
    assert parse_pct_safe(-12.5) == -12.5
    assert parse_pct_safe("-7.25%") == -7.25
    assert parse_pct_safe("bad") is None


def test_quiet_digest_triggered_kpi_revenue_drop() -> None:
    triggered, reasons, debug = quiet_digest_triggered(
        {"revenue_net_wow_pct": -12.4, "orders_paid_wow_pct": -2.0},
        ops_snapshot=None,
        fx_status_payload=None,
        rules={"digest_quiet_min_revenue_drop_pct": 8.0, "digest_quiet_min_orders_drop_pct": 10.0},
    )
    assert triggered is True
    assert any("kpi_revenue_drop" in x for x in reasons)
    assert debug["revenue_net_wow_pct"] == -12.4


def test_quiet_digest_triggered_orders_drop() -> None:
    triggered, reasons, _ = quiet_digest_triggered(
        {"revenue_net_wow_pct": -1.0, "orders_paid_wow_pct": -15.0},
        ops_snapshot=None,
        fx_status_payload=None,
        rules={"digest_quiet_min_revenue_drop_pct": 8.0, "digest_quiet_min_orders_drop_pct": 10.0},
    )
    assert triggered is True
    assert any("kpi_orders_drop" in x for x in reasons)


def test_quiet_digest_triggered_ops_and_errors_and_fx() -> None:
    snapshot = {
        "unanswered_chats": {"count": 3, "threshold_hours": 2},
        "stuck_orders": {"count": 0},
        "payment_issues": {"count": 0},
        "errors": {"count": 5, "window_hours": 24},
        "inventory": {"out_of_stock": 0, "low_stock": 0},
    }
    triggered, reasons, _ = quiet_digest_triggered(
        {"revenue_net_wow_pct": 0.0, "orders_paid_wow_pct": 0.0},
        ops_snapshot=snapshot,
        fx_status_payload={"last_apply": {"at": "2025-01-02T10:00:00+00:00", "result": "failed"}},
        rules={
            "digest_quiet_min_revenue_drop_pct": 8.0,
            "digest_quiet_min_orders_drop_pct": 10.0,
            "digest_quiet_send_on_ops": True,
            "digest_quiet_send_on_fx_failed": True,
            "digest_quiet_send_on_errors": True,
            "ops_unanswered_enabled": True,
            "ops_unanswered_min_count": 1,
            "ops_unanswered_threshold_hours": 2,
            "ops_errors_enabled": True,
            "ops_errors_min_count": 2,
            "ops_errors_window_hours": 24,
        },
    )
    assert triggered is True
    assert any(x.startswith("ops:unanswered") for x in reasons)
    assert "fx_failed" in reasons


def test_quiet_digest_triggered_no_anomaly_returns_false() -> None:
    triggered, reasons, _ = quiet_digest_triggered(
        {"revenue_net_wow_pct": -2.0, "orders_paid_wow_pct": -3.0},
        ops_snapshot={
            "unanswered_chats": {"count": 0},
            "stuck_orders": {"count": 0},
            "payment_issues": {"count": 0},
            "errors": {"count": 0},
            "inventory": {"out_of_stock": 0, "low_stock": 0},
        },
        fx_status_payload={"last_apply": {"at": "2025-01-02T10:00:00+00:00", "result": "noop"}},
        rules={"digest_quiet_send_on_ops": True, "digest_quiet_send_on_fx_failed": True, "digest_quiet_send_on_errors": True},
    )
    assert triggered is False
    assert reasons == []


def test_should_attempt_digest_quiet_rules() -> None:
    assert should_attempt_digest_quiet(
        now_local=datetime(2025, 1, 2, 8, 0),
        last_sent_local=None,
        last_attempt_local=None,
        digest_time_local="09:00",
        attempt_interval_minutes=60,
    ) is False
    assert should_attempt_digest_quiet(
        now_local=datetime(2025, 1, 2, 9, 1),
        last_sent_local=None,
        last_attempt_local=None,
        digest_time_local="09:00",
        attempt_interval_minutes=60,
    ) is True
    assert should_attempt_digest_quiet(
        now_local=datetime(2025, 1, 2, 9, 30),
        last_sent_local=None,
        last_attempt_local=datetime(2025, 1, 2, 9, 0),
        digest_time_local="09:00",
        attempt_interval_minutes=60,
    ) is False
    assert should_attempt_digest_quiet(
        now_local=datetime(2025, 1, 2, 10, 1),
        last_sent_local=None,
        last_attempt_local=datetime(2025, 1, 2, 9, 0),
        digest_time_local="09:00",
        attempt_interval_minutes=60,
    ) is True


def test_should_force_heartbeat() -> None:
    now = datetime(2025, 1, 10, tzinfo=timezone.utc)
    assert should_force_heartbeat(now, None, 7) is True
    assert should_force_heartbeat(now, datetime(2025, 1, 1, tzinfo=timezone.utc), 7) is True
    assert should_force_heartbeat(now, datetime(2025, 1, 5, tzinfo=timezone.utc), 7) is False


def test_build_critical_snapshot_thresholds_and_toggles() -> None:
    settings = SimpleNamespace(
        escalation_on_fx_failed=True,
        escalation_on_out_of_stock=True,
        escalation_on_stuck_orders_severe=True,
        escalation_on_errors_spike=True,
        escalation_on_unanswered_chats_severe=False,
        escalation_stuck_orders_min=3,
        escalation_errors_min=5,
        escalation_unanswered_chats_min=5,
        escalation_unanswered_threshold_hours=6,
    )
    snapshot = build_critical_snapshot(
        fx_status_payload={"last_apply": {"at": "2025-01-02T10:00:00+00:00", "result": "failed"}},
        ops_snapshot={
            "inventory": {"out_of_stock": 2, "top_out": [{"product_id": "p1"}]},
            "stuck_orders": {"count": 3, "top": [{"order_id": "o1"}]},
            "errors": {"count": 5, "top": [{"id": "e1"}]},
            "unanswered_chats": {"count": 10, "threshold_hours": 2, "top": [{"thread_id": "t1"}]},
        },
        notify_settings=settings,
    )
    assert snapshot["fx_failed"] is True
    assert snapshot["out_of_stock"] == 2
    assert snapshot["stuck_orders"] == 3
    assert snapshot["errors"] == 5
    assert snapshot["unanswered_chats"] == 0


def test_make_critical_event_key_stable() -> None:
    snapshot = {
        "fx_failed": True,
        "out_of_stock": 1,
        "stuck_orders": 3,
        "errors": 6,
        "unanswered_chats": 0,
        "reasons": ["fx_failed", "errors=6"],
        "top": {"errors": ["e1", "e2"]},
    }
    assert make_critical_event_key(snapshot) == make_critical_event_key(dict(snapshot))


def test_should_send_escalation_rules() -> None:
    now = datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc)
    cfg = {"stage1_after_minutes": 120, "repeat_every_minutes": 360, "max_repeats": 3}
    state = {
        "last_event_key": "k1",
        "first_seen_at": datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc),
        "last_sent_at": None,
        "repeat_count": 0,
        "last_ack_key": None,
        "snoozed_until": None,
    }
    ok, stage, _ = should_send_escalation(now, "k1", state, cfg)
    assert ok is True and stage == 1

    state["last_sent_at"] = datetime(2025, 1, 2, 11, 0, tzinfo=timezone.utc)
    state["repeat_count"] = 1
    ok, _, reason = should_send_escalation(now, "k1", state, cfg)
    assert ok is False and reason == "repeat_cooldown"

    state["last_ack_key"] = "k1"
    ok, _, reason = should_send_escalation(now, "k1", state, cfg)
    assert ok is False and reason == "acked"

    state["last_ack_key"] = None
    state["snoozed_until"] = datetime(2025, 1, 2, 13, 0, tzinfo=timezone.utc)
    ok, _, reason = should_send_escalation(now, "k1", state, cfg)
    assert ok is False and reason == "snoozed"
