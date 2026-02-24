from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.storage.models import OwnerbotAuditEvent
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


def _truncate_payload(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
    return raw[:300] + ("…" if len(raw) > 300 else "")


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    stmt = (
        select(OwnerbotAuditEvent)
        .where(
            or_(
                OwnerbotAuditEvent.event_type.ilike("%failed%"),
                OwnerbotAuditEvent.event_type.ilike("%error%"),
                OwnerbotAuditEvent.event_type.ilike("%unavailable%"),
            )
        )
        .order_by(OwnerbotAuditEvent.occurred_at.desc())
        .limit(payload.limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    events = []
    for row in rows:
        try:
            parsed = json.loads(row.payload_json)
        except json.JSONDecodeError:
            parsed = row.payload_json
        events.append(
            {
                "id": row.id,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "correlation_id": row.correlation_id,
                "event_type": row.event_type,
                "payload_preview": _truncate_payload(parsed),
            }
        )
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={"count": len(events), "events": events},
        provenance=ToolProvenance(
            sources=["ownerbot_audit_events"],
            window={"scope": "audit_log", "type": "errors"},
            filters_hash=f"errors;limit:{payload.limit}",
        ),
    )
