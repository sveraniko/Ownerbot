from __future__ import annotations

from app.core.redis import get_redis

_ANCHOR_KEY_PREFIX = "ob:ui:anchor:"
_ANCHOR_TTL_SECONDS = 604800


async def get_anchor_message_id(chat_id: int) -> int | None:
    try:
        redis = await get_redis()
        raw = await redis.get(f"{_ANCHOR_KEY_PREFIX}{chat_id}")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def set_anchor_message_id(chat_id: int, message_id: int) -> None:
    try:
        redis = await get_redis()
        await redis.set(f"{_ANCHOR_KEY_PREFIX}{chat_id}", str(message_id), ex=_ANCHOR_TTL_SECONDS)
    except Exception:
        return


async def clear_anchor_message_id(chat_id: int) -> None:
    try:
        redis = await get_redis()
        if hasattr(redis, "delete"):
            await redis.delete(f"{_ANCHOR_KEY_PREFIX}{chat_id}")
            return
        await redis.set(f"{_ANCHOR_KEY_PREFIX}{chat_id}", "", ex=1)
    except Exception:
        return
