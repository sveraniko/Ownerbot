from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import or_, select

from app.core.time import utcnow
from app.storage.models import OwnerbotDemoChatThread
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    pass


def _age_hours(now: datetime, last_customer_message_at: datetime) -> float:
    msg_at = last_customer_message_at
    if msg_at.tzinfo is None:
        msg_at = msg_at.replace(tzinfo=now.tzinfo)
    return round((now - msg_at).total_seconds() / 3600, 2)


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    del payload
    now = utcnow()
    stmt = (
        select(OwnerbotDemoChatThread)
        .where(OwnerbotDemoChatThread.open.is_(True))
        .where(
            or_(
                OwnerbotDemoChatThread.last_manager_reply_at.is_(None),
                OwnerbotDemoChatThread.last_manager_reply_at < OwnerbotDemoChatThread.last_customer_message_at,
            )
        )
        .order_by(OwnerbotDemoChatThread.last_customer_message_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()

    overdue = [
        {
            "thread_id": row.thread_id,
            "age_hours": _age_hours(now, row.last_customer_message_at),
        }
        for row in rows
    ]
    overdue.sort(key=lambda item: item["age_hours"], reverse=True)

    unanswered_2h = sum(1 for item in overdue if item["age_hours"] >= 2)
    unanswered_6h = sum(1 for item in overdue if item["age_hours"] >= 6)
    unanswered_24h = sum(1 for item in overdue if item["age_hours"] >= 24)

    if unanswered_24h > 0:
        recommendation = "Есть критические обращения старше 24ч — приоритизируйте ответ и эскалацию."
    elif unanswered_6h > 0:
        recommendation = "Очередь проседает по SLA 6ч — перераспределите нагрузку по сменам."
    elif unanswered_2h > 0:
        recommendation = "Есть обращения вне SLA 2ч — закройте хвост до конца текущего слота."
    else:
        recommendation = "Очередь в норме, SLA соблюдается."

    data = {
        "total_open_threads": len(overdue),
        "unanswered_2h": unanswered_2h,
        "unanswered_6h": unanswered_6h,
        "unanswered_24h": unanswered_24h,
        "top_overdue_threads": overdue[:5],
        "recommendation": recommendation,
    }
    provenance = ToolProvenance(
        sources=["ownerbot_demo_chat_threads", "local_demo"],
        window={"scope": "support_queue", "type": "snapshot", "as_of": now.isoformat(), "sla_hours": [2, 6, 24]},
        filters_hash="open:true;needs_reply:true",
    )
    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)
