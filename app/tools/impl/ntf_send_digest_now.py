from __future__ import annotations

from pydantic import BaseModel

from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.impl import sis_fx_status
from app.notify import extract_fx_rate_and_schedule


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    fx_response = await sis_fx_status.handle(sis_fx_status.Payload(), correlation_id=correlation_id, session=session)
    fx_line = "FX: N/A"
    if fx_response.status == "ok":
        snapshot = extract_fx_rate_and_schedule(fx_response.data)
        if snapshot.effective_rate is not None:
            fx_line = f"FX: {snapshot.effective_rate:.4f}"
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "message": f"🧪 Digest now\nKPI today/yesterday: N/A\nKPI 7d: N/A\n{fx_line}",
        },
        provenance=ToolProvenance(sources=["sis_fx_status", "owner_notify_settings"]),
    )
