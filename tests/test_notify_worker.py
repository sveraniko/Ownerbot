from types import SimpleNamespace
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.tasks.notify_worker import NotifyWorker
from app.storage.models import Base, OwnerNotifySettings


class FakeRedis:
    def __init__(self, lock: bool = True):
        self.lock = lock
        self.value = None

    async def set(self, key, value, ex=None, nx=None):
        if nx and self.lock:
            self.value = value
            self.lock = False
            return True
        return False

    async def get(self, key):
        return self.value

    async def delete(self, key):
        self.value = None


@pytest.mark.asyncio
async def test_notify_worker_skips_when_lock_not_acquired(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock())
    worker = NotifyWorker(bot)

    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(return_value=FakeRedis(lock=False)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[1]))

    await worker.tick()
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_worker_no_state_update_on_send_failure(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        session.add(
            OwnerNotifySettings(
                owner_id=7,
                fx_delta_enabled=True,
                fx_delta_min_percent=0.1,
                fx_delta_cooldown_hours=1,
                fx_delta_last_notified_rate=1.0,
            )
        )
        await session.commit()

    @asynccontextmanager
    async def fake_scope():
        async with async_session() as s:
            yield s

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("boom")))
    worker = NotifyWorker(bot)

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(return_value=FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[7]))
    monkeypatch.setattr(
        "app.core.tasks.notify_worker.sis_fx_status.handle",
        AsyncMock(return_value=SimpleNamespace(status="ok", data={"effective_rate": 1.2})),
    )

    await worker.tick()

    async with async_session() as session:
        row = await session.get(OwnerNotifySettings, 7)
        assert row.fx_delta_last_notified_at is None


@pytest.mark.asyncio
async def test_safe_send_retries_on_429(monkeypatch):
    class RetryAfterError(Exception):
        def __init__(self):
            self.retry_after = 0

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[RetryAfterError(), None]))
    worker = NotifyWorker(bot)

    sent = await worker._safe_send(1, "hello")
    assert sent is True
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_notify_worker_sends_when_lock_acquired(monkeypatch):
    bot = SimpleNamespace(send_message=AsyncMock())
    worker = NotifyWorker(bot)

    class DummySettings:
        fx_delta_enabled = True
        fx_delta_min_percent = 0.1
        fx_delta_cooldown_hours = 1
        fx_delta_last_notified_rate = 1.0
        fx_delta_last_notified_at = None
        fx_delta_last_seen_sis_event_at = None
        digest_enabled = False
        digest_tz = "Europe/Berlin"
        digest_time_local = "09:00"
        digest_last_sent_at = None
        last_error_notice_at = None

    class FakeSession:
        async def commit(self):
            return None

    @asynccontextmanager
    async def fake_scope():
        yield FakeSession()

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(return_value=FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[1]))
    monkeypatch.setattr(
        "app.core.tasks.notify_worker.NotificationSettingsService.get_or_create",
        AsyncMock(return_value=DummySettings()),
    )
    monkeypatch.setattr(
        "app.core.tasks.notify_worker.sis_fx_status.handle",
        AsyncMock(return_value=SimpleNamespace(status="ok", data={"effective_rate": 1.2})),
    )

    await worker.tick()
    assert bot.send_message.await_count == 1
