from __future__ import annotations

from sqlalchemy import select

from app.storage.models import OwnerbotActionLog


async def check_idempotency(session, idempotency_key: str) -> OwnerbotActionLog | None:
    result = await session.execute(
        select(OwnerbotActionLog).where(OwnerbotActionLog.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


async def record_action(
    session,
    idempotency_key: str,
    tool: str,
    payload_hash: str,
    status: str,
    correlation_id: str,
) -> OwnerbotActionLog:
    entry = OwnerbotActionLog(
        idempotency_key=idempotency_key,
        tool=tool,
        payload_hash=payload_hash,
        status=status,
        correlation_id=correlation_id,
    )
    session.add(entry)
    await session.commit()
    return entry
