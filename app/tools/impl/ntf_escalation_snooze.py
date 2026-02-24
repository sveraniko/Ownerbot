from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.notify import NotificationSettingsService
from app.notify.engine import clamp_int
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    hours: int = Field(default=12, ge=1, le=72)


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    settings = await NotificationSettingsService.get_or_create(session, actor.owner_user_id)
    hours = clamp_int(payload.hours, min_value=1, max_value=72)
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    settings.escalation_snoozed_until = until
    await session.commit()
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"owner_id": actor.owner_user_id, "hours": hours, "escalation_snoozed_until": until.isoformat(), "message": f"Snoozed until {until.isoformat()}"},
        provenance=ToolProvenance(sources=["owner_notify_settings"], window={"scope": "all_time", "type": "snapshot"}),
    )
