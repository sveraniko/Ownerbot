from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.storage.models import OwnerbotDemoChatThread
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    limit: int = Field(10, ge=1, le=50)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    stmt = (
        select(OwnerbotDemoChatThread)
        .where(OwnerbotDemoChatThread.open.is_(True))
        .where(
            or_(
                OwnerbotDemoChatThread.last_manager_reply_at.is_(None),
                OwnerbotDemoChatThread.last_manager_reply_at < OwnerbotDemoChatThread.last_customer_message_at,
            )
        )
        .order_by(OwnerbotDemoChatThread.last_customer_message_at.desc())
        .limit(payload.limit)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    data = {
        "count": len(rows),
        "threads": [
            {
                "thread_id": row.thread_id,
                "customer_id": row.customer_id,
                "last_customer_message_at": row.last_customer_message_at.isoformat(),
                "last_manager_reply_at": row.last_manager_reply_at.isoformat() if row.last_manager_reply_at else None,
            }
            for row in rows
        ],
    }
    provenance = ToolProvenance(
        sources=["ownerbot_demo_chat_threads", "local_demo"],
        window=None,
        filters_hash="demo",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
