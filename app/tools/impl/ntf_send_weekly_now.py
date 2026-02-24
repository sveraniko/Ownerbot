from __future__ import annotations

from pydantic import BaseModel

from app.notify import build_weekly_digest
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    del payload
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    bundle = await build_weekly_digest(actor.owner_user_id, session, correlation_id)
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"owner_id": actor.owner_user_id, "message": bundle.text, "warnings": bundle.warnings},
        provenance=ToolProvenance(sources=["owner_notify_settings", "kpi_compare", "revenue_trend", "orders_search", "chats_unanswered"], window={"scope": "7d", "type": "rolling"}),
    )
