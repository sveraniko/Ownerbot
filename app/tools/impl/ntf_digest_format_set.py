from __future__ import annotations

from pydantic import BaseModel

from app.notify import NotificationSettingsService, normalize_digest_format
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    format: str = "text"


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    digest_format = normalize_digest_format(payload.format)
    settings = await NotificationSettingsService.set_digest_format(session, actor.owner_user_id, digest_format=digest_format)
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "digest_format": settings.digest_format,
            "message": f"Формат daily digest установлен: {settings.digest_format}.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings"]),
    )
