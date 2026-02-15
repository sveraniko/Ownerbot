from __future__ import annotations

from pydantic import BaseModel, Field

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    day_of_week: int = Field(0, ge=0, le=6)
    time_local: str = "09:30"
    tz: str | None = None


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    settings = await NotificationSettingsService.set_weekly(
        session,
        actor.owner_user_id,
        enabled=True,
        day_of_week=payload.day_of_week,
        time_local=payload.time_local,
        tz=payload.tz,
    )
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "weekly_enabled": settings.weekly_enabled,
            "weekly_day_of_week": settings.weekly_day_of_week,
            "weekly_time_local": settings.weekly_time_local,
            "weekly_tz": settings.weekly_tz,
            "message": "Еженедельный отчёт включен.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings"]),
    )
