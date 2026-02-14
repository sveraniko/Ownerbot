from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.storage.models import OwnerbotAuditEvent
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    result = await session.execute(
        select(OwnerbotAuditEvent).order_by(OwnerbotAuditEvent.occurred_at.desc()).limit(payload.limit)
    )
    rows = result.scalars().all()
    events = []
    for row in rows:
        try:
            parsed = json.loads(row.payload_json)
        except json.JSONDecodeError:
            parsed = {"raw": row.payload_json}
        events.append(
            {
                "id": row.id,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "correlation_id": row.correlation_id,
                "event_type": row.event_type,
                "payload": parsed,
            }
        )
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"count": len(events), "events": events},
        provenance=ToolProvenance(sources=["ownerbot_audit_events"], filters_hash=f"limit:{payload.limit}"),
    )
