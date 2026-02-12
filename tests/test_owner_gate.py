import asyncio

import pytest

from app.bot.middlewares.owner_gate import OwnerGateMiddleware
from app.core.settings import Settings


class DummyUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class DummyEvent:
    def __init__(self, user_id: int) -> None:
        self.from_user = DummyUser(user_id)


@pytest.mark.asyncio
async def test_owner_gate(monkeypatch):
    settings = Settings(
        BOT_TOKEN="x",
        OWNER_IDS=[1],
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/0",
        ACCESS_DENY_AUDIT_ENABLED=False,
        ACCESS_DENY_NOTIFY_ONCE=False,
    )
    monkeypatch.setattr("app.core.settings.get_settings", lambda: settings)

    called = False

    async def handler(event, data):
        nonlocal called
        called = True
        return "ok"

    middleware = OwnerGateMiddleware()
    event = DummyEvent(user_id=2)
    result = await middleware(handler, event, {})

    assert result is None
    assert called is False
