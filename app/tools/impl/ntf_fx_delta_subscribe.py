from __future__ import annotations

from pydantic import BaseModel, Field

from app.notify import NotificationSettingsService, extract_fx_rate_and_schedule
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.impl import sis_fx_status


class Payload(BaseModel):
    min_percent: float | None = Field(default=None, ge=0.01)
    cooldown_hours: int | None = Field(default=None, ge=1, le=168)


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    rate = None
    status = await sis_fx_status.handle(sis_fx_status.Payload(), correlation_id=correlation_id, session=session)
    if status.status == "ok":
        rate = extract_fx_rate_and_schedule(status.data).effective_rate

    settings = await NotificationSettingsService.set_fx_delta(
        session,
        actor.owner_user_id,
        enabled=True,
        min_percent=payload.min_percent,
        cooldown_hours=payload.cooldown_hours,
        last_notified_rate=rate,
    )
    data = {
        "owner_id": actor.owner_user_id,
        "fx_delta_enabled": True,
        "fx_delta_min_percent": float(settings.fx_delta_min_percent),
        "fx_delta_cooldown_hours": settings.fx_delta_cooldown_hours,
        "fx_delta_last_notified_rate": float(settings.fx_delta_last_notified_rate) if settings.fx_delta_last_notified_rate else None,
        "message": "FX delta уведомления включены.",
    }
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=ToolProvenance(sources=["owner_notify_settings", "sis_fx_status"]))
