from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from redis.asyncio import Redis

from app.core.settings import get_settings

_redis: Redis | "InMemoryRedis" | None = None


class InMemoryRedis:
    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}

    async def get(self, key: str) -> Optional[str]:
        await self._prune(key)
        value = self._store.get(key)
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self._store[key] = value
        if ex is not None:
            self._expiry[key] = asyncio.get_event_loop().time() + ex

    async def ping(self) -> bool:
        return True

    async def _prune(self, key: str) -> None:
        if key in self._expiry and asyncio.get_event_loop().time() >= self._expiry[key]:
            self._expiry.pop(key, None)
            self._store.pop(key, None)


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    if isinstance(_redis, InMemoryRedis):
        raise RuntimeError("InMemoryRedis configured in production path")
    return _redis


async def get_test_redis() -> InMemoryRedis:
    global _redis
    if _redis is None or not isinstance(_redis, InMemoryRedis):
        _redis = InMemoryRedis()
    return _redis


async def check_redis() -> bool:
    redis_client = await get_redis()
    pong = await redis_client.ping()
    return bool(pong)
