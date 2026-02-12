import asyncio

from app.bot.services.access_audit import should_audit_denied


class FakeRedis:
    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    async def exists(self, key: str) -> int:
        return int(key in self._keys)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._keys[key] = value


def test_should_audit_denied_with_redis_throttle() -> None:
    redis = FakeRedis()

    first = asyncio.run(should_audit_denied(redis, user_id=42, update_kind="message", ttl=60))
    second = asyncio.run(should_audit_denied(redis, user_id=42, update_kind="message", ttl=60))

    assert first is True
    assert second is False
