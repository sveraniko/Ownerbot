from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse, ToolWarning


class Payload(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    dry_run: bool = True
    silent: bool = False


def _render_message(message: str, correlation_id: str, actor: ToolActor | None) -> str:
    owner_user_id = actor.owner_user_id if actor else "unknown"
    return f"OwnerBot → Team\nОт: {owner_user_id}\nID: {correlation_id}\n\n{message}"


async def handle(
    payload: Payload,
    correlation_id: str,
    session,
    actor: ToolActor | None = None,
    bot: Any | None = None,
) -> ToolResponse:
    settings = get_settings()
    manager_chat_ids = list(settings.manager_chat_ids or [])
    if not manager_chat_ids:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="CONFIG_MISSING",
            message="MANAGER_CHAT_IDS is not set",
        )

    provenance = ToolProvenance(sources=["ownerbot_config:MANAGER_CHAT_IDS", "local_ownerbot"], window={"scope": "snapshot", "type": "snapshot"})
    rendered_message = _render_message(payload.message, correlation_id, actor)

    if payload.dry_run:
        data = {
            "dry_run": True,
            "recipients": manager_chat_ids,
            "message_preview": rendered_message,
            "note": "Требует подтверждения",
        }
        return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)

    if bot is None:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="BOT_CONTEXT_MISSING",
            message="Bot context is required for delivery",
        )

    sent: list[int] = []
    failed: list[dict[str, Any]] = []
    for chat_id in manager_chat_ids:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=rendered_message,
                disable_notification=payload.silent,
            )
            sent.append(chat_id)
        except Exception as exc:
            failed.append({"chat_id": chat_id, "error": str(exc)})

    data = {
        "sent": sent,
        "failed": failed,
        "message": f"Delivered to {len(sent)} of {len(manager_chat_ids)} recipients.",
    }

    if not sent and failed:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="DELIVERY_FAILED",
            message="Failed to deliver to all recipients",
            details=data,
        )

    warnings = []
    if failed:
        warnings.append(
            ToolWarning(code="PARTIAL_DELIVERY", message="Failed to deliver to some recipients.")
        )

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data=data,
        provenance=provenance,
        warnings=warnings or None,
    )
