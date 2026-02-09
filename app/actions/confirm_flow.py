from __future__ import annotations

import hashlib
import json
import uuid

from app.core.redis import get_redis


async def create_confirm_token(payload: dict, ttl_seconds: int = 300) -> str:
    token = str(uuid.uuid4())
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    redis_client = await get_redis()
    await redis_client.set(
        f"confirm:{token}",
        json.dumps({"payload_hash": payload_hash, "payload": payload}),
        ex=ttl_seconds,
    )
    return token


async def get_confirm_payload(token: str) -> dict | None:
    redis_client = await get_redis()
    raw = await redis_client.get(f"confirm:{token}")
    if not raw:
        return None
    return json.loads(raw)
