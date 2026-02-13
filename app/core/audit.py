from __future__ import annotations

import json
import logging

from app.core.db import session_scope
from app.core.logging import get_correlation_id

logger = logging.getLogger(__name__)


async def write_audit_event(
    event_type: str,
    payload: dict,
    correlation_id: str | None = None,
) -> None:
    from app.storage.models import OwnerbotAuditEvent

    resolved_correlation_id = correlation_id or get_correlation_id()
    try:
        async with session_scope() as session:
            event = OwnerbotAuditEvent(
                correlation_id=resolved_correlation_id,
                event_type=event_type,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
            session.add(event)
            await session.commit()
    except Exception:
        logger.warning("audit_write_failed", extra={"event_type": event_type, "correlation_id": resolved_correlation_id})
