from __future__ import annotations

import re

from pydantic import BaseModel

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class Payload(BaseModel):
    time_local: str | None = None
    tz: str | None = None


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    if payload.time_local is not None and not _TIME_RE.match(payload.time_local):
        return ToolResponse.fail(correlation_id=correlation_id, code="VALIDATION_ERROR", message="time_local must be HH:MM")
    settings = await NotificationSettingsService.set_digest(
        session,
        actor.owner_user_id,
        enabled=True,
        time_local=payload.time_local,
        tz=payload.tz,
    )
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "digest_enabled": True,
            "digest_time_local": settings.digest_time_local,
            "digest_tz": settings.digest_tz,
            "message": "Ежедневный дайджест включен.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings"], window={"scope": "all_time", "type": "snapshot"}),
    )
