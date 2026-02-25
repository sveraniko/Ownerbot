from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.redis import get_redis


_LAST_ADVICE_TTL_SECONDS = 30 * 60


def _last_advice_key(chat_id: int) -> str:
    return f"ownerbot:advice:last:{chat_id}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def save_last_advice(chat_id: int, payload: dict[str, Any]) -> None:
    redis = await get_redis()
    await redis.set(_last_advice_key(chat_id), json.dumps(payload, ensure_ascii=False), ex=_LAST_ADVICE_TTL_SECONDS)


async def load_last_advice(chat_id: int) -> dict[str, Any] | None:
    redis = await get_redis()
    raw = await redis.get(_last_advice_key(chat_id))
    if not raw:
        return None
    payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    if not isinstance(payload, dict):
        return None
    return payload
