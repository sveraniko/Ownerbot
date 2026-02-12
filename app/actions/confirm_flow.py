from __future__ import annotations

import hashlib
import json
import uuid

from app.core.contracts import CONFIRM_CB_PREFIX, CONFIRM_TOKEN_RETAIN_TTL_SEC_DEFAULT
from app.core.redis import get_redis


def compute_payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


async def create_confirm_token(payload: dict, ttl_seconds: int = 300) -> str:
    token = str(uuid.uuid4())
    payload_hash = compute_payload_hash(payload)
    redis_client = await get_redis()
    await redis_client.set(
        f"{CONFIRM_CB_PREFIX}{token}",
        json.dumps({"payload_hash": payload_hash, "payload": payload}),
        ex=ttl_seconds,
    )
    return token


async def get_confirm_payload(token: str) -> dict | None:
    redis_client = await get_redis()
    raw = await redis_client.get(f"{CONFIRM_CB_PREFIX}{token}")
    if not raw:
        return None
    return json.loads(raw)


async def expire_confirm_token(
    token: str, ttl_seconds: int = CONFIRM_TOKEN_RETAIN_TTL_SEC_DEFAULT
) -> None:
    redis_client = await get_redis()
    await redis_client.expire(f"{CONFIRM_CB_PREFIX}{token}", ttl_seconds)
