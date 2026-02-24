from __future__ import annotations

from pydantic import BaseModel

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    del payload
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    settings = await NotificationSettingsService.set_digest_quiet_mode(
        session,
        actor.owner_user_id,
        enabled=False,
    )
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "digest_quiet_enabled": settings.digest_quiet_enabled,
            "message": "Quiet daily digest выключен.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings"], window={"scope": "all_time", "type": "snapshot"}),
    )
