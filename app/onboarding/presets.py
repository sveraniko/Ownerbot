from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PresetName = Literal["minimal", "standard", "aggressive"]


@dataclass(frozen=True)
class OnboardPreset:
    name: PresetName
    title: str
    values: dict[str, object]


PRESETS: dict[PresetName, OnboardPreset] = {
    "minimal": OnboardPreset(
        name="minimal",
        title="Minimal",
        values={
            "digest_enabled": False,
            "weekly_enabled": True,
            "weekly_day_of_week": 0,
            "weekly_time_local": "09:30",
            "digest_format": "pdf",
            "digest_quiet_enabled": False,
            "ops_alerts_enabled": False,
            "fx_delta_enabled": False,
            "fx_apply_events_enabled": True,
            "fx_apply_notify_applied": False,
            "fx_apply_notify_noop": False,
            "fx_apply_notify_failed": True,
            "fx_apply_events_cooldown_hours": 12,
        },
    ),
    "standard": OnboardPreset(
        name="standard",
        title="Standard",
        values={
            "digest_enabled": True,
            "digest_time_local": "09:00",
            "digest_format": "text",
            "digest_quiet_enabled": True,
            "digest_quiet_attempt_interval_minutes": 60,
            "digest_quiet_max_silence_days": 7,
            "digest_quiet_min_revenue_drop_pct": 8.0,
            "digest_quiet_min_orders_drop_pct": 10.0,
            "ops_alerts_enabled": True,
            "ops_alerts_cooldown_hours": 8,
            "fx_delta_enabled": True,
            "fx_delta_min_percent": 0.5,
            "fx_delta_cooldown_hours": 8,
            "fx_apply_events_enabled": True,
            "fx_apply_notify_applied": False,
            "fx_apply_notify_noop": False,
            "fx_apply_notify_failed": True,
            "fx_apply_events_cooldown_hours": 8,
            "weekly_enabled": True,
            "weekly_day_of_week": 0,
            "weekly_time_local": "09:30",
        },
    ),
    "aggressive": OnboardPreset(
        name="aggressive",
        title="Aggressive",
        values={
            "digest_enabled": True,
            "digest_time_local": "09:00",
            "digest_format": "png",
            "digest_quiet_enabled": False,
            "ops_alerts_enabled": True,
            "ops_alerts_cooldown_hours": 6,
            "ops_unanswered_threshold_hours": 1,
            "ops_errors_min_count": 1,
            "fx_delta_enabled": True,
            "fx_delta_min_percent": 0.25,
            "fx_delta_cooldown_hours": 6,
            "fx_apply_events_enabled": True,
            "fx_apply_notify_applied": False,
            "fx_apply_notify_noop": False,
            "fx_apply_notify_failed": True,
            "fx_apply_events_cooldown_hours": 6,
            "weekly_enabled": False,
        },
    ),
}
