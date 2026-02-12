from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.storage.models import OwnerbotActionLog


async def get_action(session, idempotency_key: str) -> OwnerbotActionLog | None:
    result = await session.execute(
        select(OwnerbotActionLog).where(OwnerbotActionLog.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


async def claim_action(
    session,
    idempotency_key: str,
    tool: str,
    payload_hash: str,
    correlation_id: str,
) -> tuple[OwnerbotActionLog | None, bool]:
    entry = OwnerbotActionLog(
        idempotency_key=idempotency_key,
        tool=tool,
        payload_hash=payload_hash,
        status="in_progress",
        committed_at=None,
        correlation_id=correlation_id,
    )
    session.add(entry)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_action(session, idempotency_key)
        return existing, False
    return entry, True


async def finalize_action(
    session,
    idempotency_key: str,
    status: str,
    correlation_id: str,
) -> None:
    terminal_status = "committed" if status == "committed" else "failed"
    await session.execute(
        update(OwnerbotActionLog)
        .where(OwnerbotActionLog.idempotency_key == idempotency_key)
        .values(
            status=terminal_status,
            committed_at=datetime.now(timezone.utc),
            correlation_id=correlation_id,
        )
    )
    await session.commit()
