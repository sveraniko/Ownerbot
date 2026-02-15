from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any


ALLOWED_DIGEST_FORMATS = {"text", "png", "pdf"}
FX_APPLY_RESULTS = {"applied", "noop", "failed"}




def clamp_int(value: int | float, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = min_value
    return max(min_value, min(parsed, max_value))


def clamp_float(value: float | int, *, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = min_value
    return max(min_value, min(parsed, max_value))


def parse_pct_safe(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().replace('%', '')
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None

def parse_datetime_safe(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def extract_fx_last_apply(status_payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    last_apply = status_payload.get("last_apply")
    if not isinstance(last_apply, dict):
        return None, "missing_last_apply"

    at_value = parse_datetime_safe(last_apply.get("at") or last_apply.get("attempted_at") or last_apply.get("created_at"))
    result = last_apply.get("result")
    if not isinstance(result, str):
        return None, "last_apply_result_invalid"
    result_normalized = result.lower().strip()
    if result_normalized not in FX_APPLY_RESULTS:
        return None, "last_apply_result_unsupported"
    if at_value is None:
        return None, "last_apply_at_invalid"

    affected_count_raw = last_apply.get("affected_count")
    affected_count = int(affected_count_raw) if isinstance(affected_count_raw, (int, float, str)) and str(affected_count_raw).isdigit() else 0

    normalized = {
        "at": at_value,
        "result": result_normalized,
        "affected_count": affected_count,
        "rate": _safe_str(last_apply.get("rate") or last_apply.get("effective_rate")),
        "delta_percent": _safe_str(last_apply.get("delta_percent") or last_apply.get("delta_pct")),
        "reason": _safe_str(last_apply.get("reason")),
        "error": _safe_str(last_apply.get("error") or last_apply.get("message")),
        "from": _safe_str(last_apply.get("from") or status_payload.get("base_currency")),
        "to": _safe_str(last_apply.get("to") or status_payload.get("shop_currency")),
        "provider": _safe_str(last_apply.get("provider") or status_payload.get("provider")),
    }
    return normalized, None


def make_fx_apply_event_key(last_apply: dict[str, Any]) -> str:
    at = last_apply.get("at")
    at_iso = at.isoformat() if isinstance(at, datetime) else "n/a"
    components = [
        at_iso,
        str(last_apply.get("result") or ""),
        str(last_apply.get("affected_count") or 0),
        str(last_apply.get("rate") or ""),
        str(last_apply.get("reason") or ""),
    ]
    key = "|".join(components)
    return key[:240]


def should_send_fx_apply_event(
    now: datetime,
    last_sent_at: datetime | None,
    cooldown_hours: int,
    last_seen_key: str | None,
    event_key: str,
) -> bool:
    if not event_key:
        return False
    if last_seen_key and last_seen_key == event_key:
        return False
    if cooldown_hours < 1:
        return False
    if last_sent_at is not None and (now - last_sent_at) < timedelta(hours=cooldown_hours):
        return False
    return True


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


@dataclass
class FxStatusSnapshot:
    effective_rate: float | None
    schedule_fields: dict[str, Any]


def extract_fx_rate_and_schedule(status_payload: dict[str, Any]) -> FxStatusSnapshot:
    rate_keys = ("effective_rate", "current_rate", "resolved_rate", "latest_rate", "rate")
    effective_rate: float | None = None
    for key in rate_keys:
        value = status_payload.get(key)
        if isinstance(value, (int, float)):
            effective_rate = float(value)
            break
        if isinstance(value, str):
            try:
                effective_rate = float(value)
                break
            except ValueError:
                continue

    schedule: dict[str, Any] = {}
    for key in (
        "last_apply_success_at",
        "last_apply_attempt_at",
        "last_apply_failed_at",
        "last_apply_result",
        "would_apply",
        "next_reprice_in_hours",
    ):
        if key in status_payload:
            schedule[key] = status_payload.get(key)
    return FxStatusSnapshot(effective_rate=effective_rate, schedule_fields=schedule)


def should_send_fx_delta(
    now: datetime,
    last_rate: float | None,
    new_rate: float | None,
    min_percent: float,
    last_notified_at: datetime | None,
    cooldown_hours: int,
) -> bool:
    if new_rate is None or new_rate <= 0:
        return False
    if min_percent < 0.01:
        return False
    if cooldown_hours < 1:
        return False
    if last_notified_at is not None and (now - last_notified_at) < timedelta(hours=cooldown_hours):
        return False
    if last_rate is None or last_rate <= 0:
        return True
    delta_pct = abs((new_rate - last_rate) / last_rate) * 100
    return delta_pct >= min_percent


def should_send_digest(now_local: datetime, last_sent_at: datetime | None, digest_time_local: str) -> bool:
    target_hour, target_minute = parse_time_local_or_default(digest_time_local)

    scheduled_today = now_local.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if now_local < scheduled_today:
        return False
    if last_sent_at is None:
        return True
    return now_local.date() > last_sent_at.date()


def parse_time_local_or_default(value: str | None, default: tuple[int, int] = (9, 0)) -> tuple[int, int]:
    if not value:
        return default
    try:
        hour_str, minute_str = value.split(":", 1)
        target_hour = int(hour_str)
        target_minute = int(minute_str)
    except Exception:
        return default
    if not (0 <= target_hour <= 23 and 0 <= target_minute <= 59):
        return default
    return target_hour, target_minute


def normalize_weekly_day_of_week(day_of_week: int | None) -> int:
    if day_of_week is None:
        return 0
    if 0 <= int(day_of_week) <= 6:
        return int(day_of_week)
    return 0


def normalize_digest_format(format_value: str | None) -> str:
    if isinstance(format_value, str) and format_value.lower() in ALLOWED_DIGEST_FORMATS:
        return format_value.lower()
    return "text"


def should_send_weekly(
    now_local: datetime,
    last_sent_at_local: datetime | None,
    weekly_day_of_week: int,
    weekly_time_local: str,
) -> bool:
    normalized_day = normalize_weekly_day_of_week(weekly_day_of_week)
    target_hour, target_minute = parse_time_local_or_default(weekly_time_local, default=(9, 30))

    start_of_week = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now_local.weekday())
    scheduled_dt = start_of_week + timedelta(days=normalized_day, hours=target_hour, minutes=target_minute)

    if now_local < scheduled_dt:
        return False
    if last_sent_at_local is None:
        return True
    return now_local.isocalendar()[:2] != last_sent_at_local.isocalendar()[:2]


def _extract_top_ids(items: list[dict[str, Any]], keys: tuple[str, ...], limit: int = 3) -> list[str]:
    values: list[str] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                values.append(text)
                break
    return values


def make_ops_event_key(snapshot: dict[str, Any], rules: dict[str, Any]) -> str:
    del rules
    unanswered = snapshot.get("unanswered_chats") or {}
    stuck = snapshot.get("stuck_orders") or {}
    payment = snapshot.get("payment_issues") or {}
    errors = snapshot.get("errors") or {}
    inventory = snapshot.get("inventory") or {}

    top_ids: list[str] = []
    top_ids.extend(_extract_top_ids(unanswered.get("top") or [], ("thread_id", "customer_id")))
    top_ids.extend(_extract_top_ids(stuck.get("top") or [], ("order_id",)))
    top_ids.extend(_extract_top_ids(payment.get("top") or [], ("order_id",)))
    top_ids.extend(_extract_top_ids(errors.get("top") or [], ("id", "correlation_id")))
    top_ids.extend(_extract_top_ids(inventory.get("top_out") or [], ("product_id",)))
    top_ids.extend(_extract_top_ids(inventory.get("top_low") or [], ("product_id",)))

    now = datetime.now(timezone.utc)
    bucket = now.strftime("%Y%m%d%H")
    key = (
        f"u:{int(unanswered.get('count') or 0)}|"
        f"s:{int(stuck.get('count') or 0)}|"
        f"p:{int(payment.get('count') or 0)}|"
        f"e:{int(errors.get('count') or 0)}|"
        f"oos:{int(inventory.get('out_of_stock') or 0)}|"
        f"low:{int(inventory.get('low_stock') or 0)}|"
        f"top:{','.join(top_ids[:8])}|"
        f"b:{bucket}"
    )
    return key[:300]


def should_send_ops_alert(
    now: datetime,
    last_sent_at: datetime | None,
    cooldown_hours: int,
    last_seen_key: str | None,
    event_key: str,
) -> bool:
    if not event_key:
        return False
    if last_seen_key and last_seen_key == event_key:
        return False
    if cooldown_hours < 1:
        return False
    if last_sent_at is not None and (now - last_sent_at) < timedelta(hours=cooldown_hours):
        return False
    return True


def alert_triggered(snapshot: dict[str, Any], rules: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    unanswered = snapshot.get("unanswered_chats") or {}
    stuck = snapshot.get("stuck_orders") or {}
    payment = snapshot.get("payment_issues") or {}
    errors = snapshot.get("errors") or {}
    inventory = snapshot.get("inventory") or {}

    if rules.get("ops_unanswered_enabled", True) and int(unanswered.get("count") or 0) >= int(rules.get("ops_unanswered_min_count", 1)):
        reasons.append(f"unanswered>{int(rules.get('ops_unanswered_threshold_hours', 2))}h={int(unanswered.get('count') or 0)}")
    if rules.get("ops_stuck_orders_enabled", True) and int(stuck.get("count") or 0) >= int(rules.get("ops_stuck_orders_min_count", 1)):
        reasons.append(f"stuck={int(stuck.get('count') or 0)}")
    if rules.get("ops_payment_issues_enabled", True) and int(payment.get("count") or 0) >= int(rules.get("ops_payment_issues_min_count", 1)):
        reasons.append(f"payment_issues={int(payment.get('count') or 0)}")
    if rules.get("ops_errors_enabled", True) and int(errors.get("count") or 0) >= int(rules.get("ops_errors_min_count", 1)):
        reasons.append(f"errors({int(rules.get('ops_errors_window_hours', 24))}h)={int(errors.get('count') or 0)}")
    if rules.get("ops_out_of_stock_enabled", True) and int(inventory.get("out_of_stock") or 0) >= int(rules.get("ops_out_of_stock_min_count", 1)):
        reasons.append(f"out_of_stock={int(inventory.get('out_of_stock') or 0)}")
    if rules.get("ops_low_stock_enabled", True) and int(inventory.get("low_stock") or 0) >= int(rules.get("ops_low_stock_min_count", 3)):
        reasons.append(f"low_stock<={int(rules.get('ops_low_stock_lte', 5))}:{int(inventory.get('low_stock') or 0)}")

    return (len(reasons) > 0), reasons


def quiet_digest_triggered(
    kpi_summary: dict[str, Any],
    ops_snapshot: dict[str, Any] | None,
    fx_status_payload: dict[str, Any] | None,
    rules: dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    debug: dict[str, Any] = {}

    revenue_drop_limit = clamp_float(float(rules.get("digest_quiet_min_revenue_drop_pct", 8.0)), min_value=0.1, max_value=50.0)
    orders_drop_limit = clamp_float(float(rules.get("digest_quiet_min_orders_drop_pct", 10.0)), min_value=0.1, max_value=50.0)
    revenue_pct = parse_pct_safe(kpi_summary.get("revenue_net_wow_pct"))
    orders_pct = parse_pct_safe(kpi_summary.get("orders_paid_wow_pct"))
    debug["revenue_net_wow_pct"] = revenue_pct
    debug["orders_paid_wow_pct"] = orders_pct

    if revenue_pct is not None and revenue_pct <= -revenue_drop_limit:
        reasons.append(f"kpi_revenue_drop={revenue_pct:.1f}%<=-{revenue_drop_limit:.1f}%")
    if orders_pct is not None and orders_pct <= -orders_drop_limit:
        reasons.append(f"kpi_orders_drop={orders_pct:.1f}%<=-{orders_drop_limit:.1f}%")

    if bool(rules.get("digest_quiet_send_on_ops", True)) and ops_snapshot:
        ops_triggered, ops_reasons = alert_triggered(ops_snapshot, rules)
        if ops_triggered:
            reasons.extend([f"ops:{reason}" for reason in ops_reasons])

    if bool(rules.get("digest_quiet_send_on_errors", True)) and ops_snapshot:
        errors_count = int((ops_snapshot.get("errors") or {}).get("count") or 0)
        errors_min_count = int(rules.get("ops_errors_min_count", 1) or 1)
        errors_window_hours = int(rules.get("ops_errors_window_hours", 24) or 24)
        debug["errors_count"] = errors_count
        if errors_count >= errors_min_count:
            reason = f"ops:errors({errors_window_hours}h)={errors_count}"
            if reason not in reasons:
                reasons.append(reason)

    if bool(rules.get("digest_quiet_send_on_fx_failed", True)) and fx_status_payload:
        last_apply, warning = extract_fx_last_apply(fx_status_payload)
        debug["fx_last_apply_warning"] = warning
        if warning is None and isinstance(last_apply, dict) and str(last_apply.get("result") or "") == "failed":
            reasons.append("fx_failed")

    return (len(reasons) > 0), reasons, debug


def should_attempt_digest_quiet(
    now_local: datetime,
    last_sent_local: datetime | None,
    last_attempt_local: datetime | None,
    digest_time_local: str,
    attempt_interval_minutes: int,
) -> bool:
    target_hour, target_minute = parse_time_local_or_default(digest_time_local)
    scheduled_today = now_local.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if now_local < scheduled_today:
        return False
    if last_sent_local is not None and last_sent_local.date() == now_local.date():
        return False
    interval = clamp_int(attempt_interval_minutes, min_value=15, max_value=360)
    if last_attempt_local is None:
        return True
    return (now_local - last_attempt_local) >= timedelta(minutes=interval)


def should_force_heartbeat(now_utc: datetime, last_sent_at_utc: datetime | None, max_silence_days: int) -> bool:
    days = clamp_int(max_silence_days, min_value=1, max_value=30)
    if last_sent_at_utc is None:
        return True
    if last_sent_at_utc.tzinfo is None:
        last_sent_at_utc = last_sent_at_utc.replace(tzinfo=timezone.utc)
    return (now_utc - last_sent_at_utc) >= timedelta(days=days)
