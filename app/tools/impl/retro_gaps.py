from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.audit import write_audit_event
from app.retro.formatter import format_retro_gaps
from app.retro.service import retro_gaps_with_deltas
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    period_days: int = Field(default=30)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    if payload.period_days not in {7, 30}:
        return ToolResponse.fail(correlation_id=correlation_id, code="VALIDATION_ERROR", message="period_days must be 7 or 30")

    report = await retro_gaps_with_deltas(session, payload.period_days)
    text = format_retro_gaps(report.current)
    await write_audit_event("retro_viewed", {"period_days": payload.period_days, "kind": "gaps"}, correlation_id=correlation_id)
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "period_days": payload.period_days,
            "gaps": report.current.to_dict(),
            "previous": report.previous.to_dict(),
            "deltas": report.deltas,
            "text": text,
        },
        provenance=ToolProvenance(
            sources=["ownerbot_audit_events"],
            window={"scope": "retro", "type": "rolling", "days": payload.period_days},
            filters_hash=f"retro_gaps:{payload.period_days}",
        ),
    )
