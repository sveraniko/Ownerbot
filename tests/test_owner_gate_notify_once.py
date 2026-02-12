import pytest

from app.bot.middlewares.owner_gate import OwnerGateMiddleware
from app.core.settings import Settings


class DummyUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.username = "intruder"


class DummyChat:
    def __init__(self, chat_type: str = "private") -> None:
        self.id = 111
        self.type = chat_type


class DummyEvent:
    def __init__(self, user_id: int, chat_type: str = "private") -> None:
        self.from_user = DummyUser(user_id)
        self.chat = DummyChat(chat_type=chat_type)
        self.text = "ping"
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


class FakeRedis:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def exists(self, key: str) -> int:
        return int(key in self._keys)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._keys.add(key)


@pytest.mark.asyncio
async def test_owner_gate_notify_once_private(monkeypatch):
    settings = Settings(
        BOT_TOKEN="x",
        OWNER_IDS=[1],
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        ACCESS_DENY_AUDIT_ENABLED=False,
        ACCESS_DENY_AUDIT_TTL_SEC=60,
        ACCESS_DENY_NOTIFY_ONCE=True,
    )
    monkeypatch.setattr("app.bot.middlewares.owner_gate.get_settings", lambda: settings)
    redis = FakeRedis()
    async def fake_get_redis():
        return redis
    monkeypatch.setattr("app.bot.middlewares.owner_gate.get_redis", fake_get_redis)

    async def fake_write(event_type, payload, correlation_id=None):
        return None

    monkeypatch.setattr("app.bot.middlewares.owner_gate.write_audit_event", fake_write)

    async def handler(event, data):
        return "ok"

    middleware = OwnerGateMiddleware()
    event = DummyEvent(user_id=2, chat_type="private")

    await middleware(handler, event, {})
    await middleware(handler, event, {})

    assert event.answers == ["Нет доступа."]
