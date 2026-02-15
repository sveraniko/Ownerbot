from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


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
    try:
        hour_str, minute_str = digest_time_local.split(":", 1)
        target_hour = int(hour_str)
        target_minute = int(minute_str)
    except Exception:
        target_hour = 9
        target_minute = 0

    if not (0 <= target_hour <= 23 and 0 <= target_minute <= 59):
        target_hour = 9
        target_minute = 0

    scheduled_today = now_local.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if now_local < scheduled_today:
        return False
    if last_sent_at is None:
        return True
    return now_local.date() > last_sent_at.date()
