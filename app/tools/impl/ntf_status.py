from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.notify import NotificationSettingsService, normalize_digest_format, normalize_weekly_day_of_week, parse_time_local_or_default
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    del payload
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    settings = await NotificationSettingsService.get_or_create(session, actor.owner_user_id)
    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))

    try:
        digest_tz = ZoneInfo(settings.digest_tz)
    except Exception:
        digest_tz = ZoneInfo("Europe/Berlin")
    try:
        weekly_tz = ZoneInfo(settings.weekly_tz or settings.digest_tz)
    except Exception:
        weekly_tz = ZoneInfo("Europe/Berlin")

    digest_hh, digest_mm = parse_time_local_or_default(settings.digest_time_local)
    next_digest = now_utc.astimezone(digest_tz).replace(hour=digest_hh, minute=digest_mm, second=0, microsecond=0)
    if next_digest <= now_utc.astimezone(digest_tz):
        next_digest += timedelta(days=1)

    weekly_hh, weekly_mm = parse_time_local_or_default(settings.weekly_time_local, default=(9, 30))
    weekly_dow = normalize_weekly_day_of_week(settings.weekly_day_of_week)
    now_weekly = now_utc.astimezone(weekly_tz)
    days_ahead = (weekly_dow - now_weekly.weekday()) % 7
    next_weekly = now_weekly.replace(hour=weekly_hh, minute=weekly_mm, second=0, microsecond=0) + timedelta(days=days_ahead)
    if next_weekly <= now_weekly:
        next_weekly += timedelta(days=7)

    data = {
        "owner_id": actor.owner_user_id,
        "fx_delta_enabled": settings.fx_delta_enabled,
        "fx_delta_min_percent": float(settings.fx_delta_min_percent),
        "fx_delta_cooldown_hours": settings.fx_delta_cooldown_hours,
        "fx_delta_last_notified_rate": float(settings.fx_delta_last_notified_rate) if settings.fx_delta_last_notified_rate else None,
        "fx_apply_events_enabled": settings.fx_apply_events_enabled,
        "fx_apply_notify_applied": settings.fx_apply_notify_applied,
        "fx_apply_notify_noop": settings.fx_apply_notify_noop,
        "fx_apply_notify_failed": settings.fx_apply_notify_failed,
        "fx_apply_events_cooldown_hours": settings.fx_apply_events_cooldown_hours,
        "fx_apply_last_seen_key": settings.fx_apply_last_seen_key,
        "fx_apply_last_sent_at": settings.fx_apply_last_sent_at.isoformat() if settings.fx_apply_last_sent_at else None,
        "digest_enabled": settings.digest_enabled,
        "digest_time_local": settings.digest_time_local,
        "digest_tz": settings.digest_tz,
        "digest_format": normalize_digest_format(settings.digest_format),
        "digest_include_fx": settings.digest_include_fx,
        "digest_include_ops": settings.digest_include_ops,
        "digest_include_kpi": settings.digest_include_kpi,
        "next_digest_at_local": next_digest.isoformat(),
        "weekly_enabled": settings.weekly_enabled,
        "weekly_day_of_week": weekly_dow,
        "weekly_time_local": settings.weekly_time_local,
        "weekly_tz": settings.weekly_tz,
        "next_weekly_at_local": next_weekly.isoformat(),
        "ops_alerts_enabled": settings.ops_alerts_enabled,
        "ops_alerts_cooldown_hours": settings.ops_alerts_cooldown_hours,
        "ops_alerts_last_sent_at": settings.ops_alerts_last_sent_at.isoformat() if settings.ops_alerts_last_sent_at else None,
        "ops_rules": {
            "unanswered_threshold_hours": settings.ops_unanswered_threshold_hours,
            "unanswered_min_count": settings.ops_unanswered_min_count,
            "stuck_min_count": settings.ops_stuck_orders_min_count,
            "payment_min_count": settings.ops_payment_issues_min_count,
            "errors_window_hours": settings.ops_errors_window_hours,
            "errors_min_count": settings.ops_errors_min_count,
            "out_of_stock_min_count": settings.ops_out_of_stock_min_count,
            "low_stock_lte": settings.ops_low_stock_lte,
            "low_stock_min_count": settings.ops_low_stock_min_count,
        },
        "message": (
            f"FX Δ: {'on' if settings.fx_delta_enabled else 'off'} ({float(settings.fx_delta_min_percent):.2f}%/{settings.fx_delta_cooldown_hours}ч)\n"
            f"FX apply: {'on' if settings.fx_apply_events_enabled else 'off'} (applied={settings.fx_apply_notify_applied}, noop={settings.fx_apply_notify_noop}, failed={settings.fx_apply_notify_failed}, cd={settings.fx_apply_events_cooldown_hours}ч)\n"
            f"Digest: {'on' if settings.digest_enabled else 'off'} ({settings.digest_time_local} {settings.digest_tz}, format={normalize_digest_format(settings.digest_format)})\n"
            f"Weekly: {'on' if settings.weekly_enabled else 'off'} (dow={weekly_dow}, {settings.weekly_time_local} {settings.weekly_tz})\n"
            f"Ops alerts: {'on' if settings.ops_alerts_enabled else 'off'} (cd={settings.ops_alerts_cooldown_hours}ч, unanswered>{settings.ops_unanswered_threshold_hours}h, low<={settings.ops_low_stock_lte})"
        ),
    }
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=ToolProvenance(sources=["owner_notify_settings"]))
