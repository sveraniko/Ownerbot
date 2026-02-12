import pytest

from app.bot.middlewares.owner_gate import OwnerGateMiddleware
from app.core.settings import Settings


class DummyUser:
    def __init__(self, user_id: int, username: str = "intruder") -> None:
        self.id = user_id
        self.username = username


class DummyChat:
    def __init__(self, chat_id: int, chat_type: str = "private") -> None:
        self.id = chat_id
        self.type = chat_type


class DummyEvent:
    def __init__(self, user_id: int) -> None:
        self.from_user = DummyUser(user_id)
        self.chat = DummyChat(chat_id=700)
        self.text = "hello"


class FakeRedis:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def exists(self, key: str) -> int:
        return int(key in self._keys)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._keys.add(key)


@pytest.mark.asyncio
async def test_owner_gate_writes_access_denied_once_per_ttl(monkeypatch):
    settings = Settings(
        BOT_TOKEN="x",
        OWNER_IDS=[1],
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        ACCESS_DENY_AUDIT_ENABLED=True,
        ACCESS_DENY_AUDIT_TTL_SEC=60,
        ACCESS_DENY_NOTIFY_ONCE=False,
    )
    monkeypatch.setattr("app.bot.middlewares.owner_gate.get_settings", lambda: settings)
    redis = FakeRedis()
    async def fake_get_redis():
        return redis
    monkeypatch.setattr("app.bot.middlewares.owner_gate.get_redis", fake_get_redis)

    calls = []

    async def fake_write(event_type, payload, correlation_id=None):
        calls.append((event_type, payload, correlation_id))

    monkeypatch.setattr("app.bot.middlewares.owner_gate.write_audit_event", fake_write)

    async def handler(event, data):
        return "ok"

    middleware = OwnerGateMiddleware()
    event = DummyEvent(user_id=2)

    await middleware(handler, event, {"correlation_id": "corr-1"})
    await middleware(handler, event, {"correlation_id": "corr-2"})

    assert len(calls) == 1
    assert calls[0][0] == "access_denied"
    assert calls[0][1]["update_kind"] == "message"
