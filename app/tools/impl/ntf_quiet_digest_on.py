from __future__ import annotations

from pydantic import BaseModel, Field

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    attempt_interval_minutes: int | None = Field(default=None, ge=1)
    max_silence_days: int | None = Field(default=None, ge=1)


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    settings = await NotificationSettingsService.set_digest_quiet_mode(
        session,
        actor.owner_user_id,
        enabled=True,
        attempt_interval_minutes=payload.attempt_interval_minutes,
        max_silence_days=payload.max_silence_days,
    )
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "digest_quiet_enabled": settings.digest_quiet_enabled,
            "digest_quiet_attempt_interval_minutes": int(settings.digest_quiet_attempt_interval_minutes),
            "digest_quiet_max_silence_days": int(settings.digest_quiet_max_silence_days),
            "message": "Quiet daily digest включен.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings"]),
    )
