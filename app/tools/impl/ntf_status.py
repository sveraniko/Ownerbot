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
        "message": (
            f"FX Δ: {'on' if settings.fx_delta_enabled else 'off'} ({float(settings.fx_delta_min_percent):.2f}%/{settings.fx_delta_cooldown_hours}ч)\n"
            f"Digest: {'on' if settings.digest_enabled else 'off'} ({settings.digest_time_local} {settings.digest_tz}, format={normalize_digest_format(settings.digest_format)})\n"
            f"Weekly: {'on' if settings.weekly_enabled else 'off'} (dow={weekly_dow}, {settings.weekly_time_local} {settings.weekly_tz})"
        ),
    }
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=ToolProvenance(sources=["owner_notify_settings"]))
