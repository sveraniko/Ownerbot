from __future__ import annotations

from pydantic import BaseModel, Field

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    notify_applied: bool = False
    notify_noop: bool = False
    notify_failed: bool = True
    cooldown_hours: int = Field(default=6, ge=1, le=168)


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    settings = await NotificationSettingsService.set_fx_apply_events(
        session,
        actor.owner_user_id,
        enabled=True,
        notify_applied=payload.notify_applied,
        notify_noop=payload.notify_noop,
        notify_failed=payload.notify_failed,
        cooldown_hours=payload.cooldown_hours,
    )
    data = {
        "owner_id": actor.owner_user_id,
        "fx_apply_events_enabled": settings.fx_apply_events_enabled,
        "fx_apply_notify_applied": settings.fx_apply_notify_applied,
        "fx_apply_notify_noop": settings.fx_apply_notify_noop,
        "fx_apply_notify_failed": settings.fx_apply_notify_failed,
        "fx_apply_events_cooldown_hours": settings.fx_apply_events_cooldown_hours,
        "message": "FX apply события включены.",
    }
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=ToolProvenance(sources=["owner_notify_settings"]))
