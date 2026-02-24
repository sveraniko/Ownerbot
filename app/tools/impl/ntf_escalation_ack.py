from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    del payload
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    settings = await NotificationSettingsService.get_or_create(session, actor.owner_user_id)
    settings.escalation_last_ack_key = settings.escalation_last_event_key
    settings.escalation_last_ack_at = datetime.now(timezone.utc)
    await session.commit()
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"owner_id": actor.owner_user_id, "escalation_last_ack_key": settings.escalation_last_ack_key, "message": "Acknowledged. Escalation for current incident stopped."},
        provenance=ToolProvenance(sources=["owner_notify_settings"], window={"scope": "all_time", "type": "snapshot"}),
    )
