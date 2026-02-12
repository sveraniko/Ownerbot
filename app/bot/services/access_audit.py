from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

_MAX_IN_MEMORY_KEYS = 1000
_in_memory_throttle: OrderedDict[str, float] = OrderedDict()


def _compact_cache(now: float) -> None:
    expired = [key for key, expires_at in _in_memory_throttle.items() if expires_at <= now]
    for key in expired:
        _in_memory_throttle.pop(key, None)

    while len(_in_memory_throttle) > _MAX_IN_MEMORY_KEYS:
        _in_memory_throttle.popitem(last=False)


async def should_audit_denied(redis: Any, user_id: int, update_kind: str, ttl: int) -> bool:
    key = f"deny:{update_kind}:{user_id}"
    if redis is not None:
        try:
            exists = await redis.exists(key)
            if exists:
                return False
            await redis.setex(key, ttl, "1")
            return True
        except Exception:
            pass

    now = time.monotonic()
    _compact_cache(now)

    expires_at = _in_memory_throttle.get(key)
    if expires_at is not None and expires_at > now:
        _in_memory_throttle.move_to_end(key)
        return False

    _in_memory_throttle[key] = now + ttl
    _in_memory_throttle.move_to_end(key)
    _compact_cache(now)
    return True


def build_access_denied_payload(update: Any, reason: str, update_kind: str) -> dict[str, Any]:
    from_user = getattr(update, "from_user", None)
    chat = getattr(update, "chat", None)

    text = getattr(update, "text", None)
    callback_data = None

    if update_kind == "callback":
        message = getattr(update, "message", None)
        if message is not None:
            chat = getattr(message, "chat", chat)
        callback_data = getattr(update, "data", None)

    payload: dict[str, Any] = {
        "reason": reason,
        "update_kind": update_kind,
        "user_id": getattr(from_user, "id", None),
        "username": getattr(from_user, "username", None),
        "chat_id": getattr(chat, "id", None),
        "chat_type": getattr(chat, "type", None),
    }

    if text:
        payload["text_preview"] = str(text).replace("\n", " ")[:80]
    if callback_data:
        payload["callback_data_preview"] = str(callback_data).replace("\n", " ")[:80]

    return payload
