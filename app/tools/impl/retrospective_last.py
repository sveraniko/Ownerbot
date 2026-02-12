from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.storage.models import OwnerbotAuditEvent
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    stmt = (
        select(OwnerbotAuditEvent)
        .where(OwnerbotAuditEvent.event_type == "retrospective")
        .order_by(OwnerbotAuditEvent.occurred_at.desc())
        .limit(payload.limit)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    items = []
    for row in rows:
        try:
            parsed_payload = json.loads(row.payload_json)
        except json.JSONDecodeError:
            parsed_payload = {"raw_payload": row.payload_json}
        items.append(
            {
                "id": row.id,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "correlation_id": row.correlation_id,
                "event_type": row.event_type,
                "payload": parsed_payload,
            }
        )

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"count": len(items), "events": items},
        provenance=ToolProvenance(
            sources=["ownerbot_audit_events"],
            window={"kind": "last_n", "limit": payload.limit},
            filters_hash="event_type:retrospective",
        ),
    )
