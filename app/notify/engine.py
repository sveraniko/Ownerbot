from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


ALLOWED_DIGEST_FORMATS = {"text", "png", "pdf"}


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
