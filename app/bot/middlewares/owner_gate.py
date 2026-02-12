from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from app.bot.services.access_audit import build_access_denied_payload, should_audit_denied
from app.core.audit import write_audit_event
from app.core.redis import get_redis
from app.core.security import is_owner
from app.core.settings import get_settings

logger = logging.getLogger(__name__)


class OwnerGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        if not is_owner(user.id):
            await self._handle_denied(event, data)
            return None
        return await handler(event, data)

    async def _handle_denied(self, event: Any, data: Dict[str, Any]) -> None:
        settings = get_settings()
        update_kind = self._resolve_update_kind(event)
        redis_client = None
        try:
            redis_client = await get_redis()
        except Exception:
            redis_client = None

        should_emit = await should_audit_denied(
            redis=redis_client,
            user_id=event.from_user.id,
            update_kind=update_kind,
            ttl=settings.access_deny_audit_ttl_sec,
        )
        if not should_emit:
            return

        correlation_id = data.get("correlation_id") or str(uuid.uuid4())
        payload = build_access_denied_payload(
            update=event,
            reason="not_in_allowlist",
            update_kind=update_kind,
        )

        if settings.access_deny_audit_enabled:
            await write_audit_event(
                event_type="access_denied",
                payload=payload,
                correlation_id=correlation_id,
            )
            logger.info(
                "access_denied",
                extra={
                    "user_id": payload.get("user_id"),
                    "update_kind": update_kind,
                    "chat_id": payload.get("chat_id"),
                    "correlation_id": correlation_id,
                },
            )

        if settings.access_deny_notify_once and payload.get("chat_type") == "private":
            await self._notify_denied_once(event)

    @staticmethod
    def _resolve_update_kind(event: Any) -> str:
        if getattr(event, "data", None) is not None and getattr(event, "message", None) is not None:
            return "callback"
        return "message"

    @staticmethod
    async def _notify_denied_once(event: Any) -> None:
        answer = getattr(event, "answer", None)
        if callable(answer):
            await event.answer("Нет доступа.")
