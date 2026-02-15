from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    settings = await NotificationSettingsService.get_or_create(session, actor.owner_user_id)
    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    try:
        tz = ZoneInfo(settings.digest_tz)
    except Exception:
        tz = ZoneInfo("Europe/Berlin")
    next_digest = now_utc.astimezone(tz).replace(second=0, microsecond=0)
    hh, mm = [int(v) for v in settings.digest_time_local.split(":", 1)]
    next_digest = next_digest.replace(hour=hh, minute=mm)
    if next_digest <= now_utc.astimezone(tz):
        from datetime import timedelta

        next_digest += timedelta(days=1)

    data = {
        "owner_id": actor.owner_user_id,
        "fx_delta_enabled": settings.fx_delta_enabled,
        "fx_delta_min_percent": float(settings.fx_delta_min_percent),
        "fx_delta_cooldown_hours": settings.fx_delta_cooldown_hours,
        "fx_delta_last_notified_rate": float(settings.fx_delta_last_notified_rate) if settings.fx_delta_last_notified_rate else None,
        "digest_enabled": settings.digest_enabled,
        "digest_time_local": settings.digest_time_local,
        "digest_tz": settings.digest_tz,
        "next_digest_at_local": next_digest.isoformat(),
        "message": (
            f"FX Δ: {'on' if settings.fx_delta_enabled else 'off'} (порог {float(settings.fx_delta_min_percent):.2f}%, "
            f"кулдаун {settings.fx_delta_cooldown_hours}ч)\n"
            f"Digest: {'on' if settings.digest_enabled else 'off'} ({settings.digest_time_local} {settings.digest_tz})"
        ),
    }
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=ToolProvenance(sources=["owner_notify_settings"]))
