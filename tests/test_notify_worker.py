from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock(), send_document=AsyncMock())
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
        session.add(OwnerNotifySettings(owner_id=7, digest_enabled=True, digest_time_local="00:00", digest_tz="UTC", digest_format="text"))
        await session.commit()

    @asynccontextmanager
    async def fake_scope():
        async with async_session() as s:
            yield s

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("boom")), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(return_value=FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[7]))
    monkeypatch.setattr(
        "app.core.tasks.notify_worker.build_daily_digest",
        AsyncMock(return_value=SimpleNamespace(text="digest", series=[], kpi_summary={}, ops_summary={}, fx_summary={}, warnings=[])),
    )

    await worker.tick()

    async with async_session() as session:
        row = await session.get(OwnerNotifySettings, 7)
        assert row.digest_last_sent_at is None


@pytest.mark.asyncio
async def test_safe_send_retries_on_429():
    class RetryAfterError(Exception):
        def __init__(self):
            self.retry_after = 0

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[RetryAfterError(), None]), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    sent = await worker._safe_send_message(1, "hello")
    assert sent is True
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_digest_png_uses_photo_and_updates_state(monkeypatch):
    class DummySettings:
        fx_delta_enabled = False
        digest_enabled = True
        digest_tz = "UTC"
        digest_time_local = "00:00"
        digest_last_sent_at = None
        digest_format = "png"
        weekly_enabled = False
        weekly_tz = "UTC"
        weekly_time_local = "09:30"
        weekly_day_of_week = 0
        weekly_last_sent_at = None
        last_error_notice_at = None

    class FakeSession:
        committed = False

        async def commit(self):
            self.committed = True

    fake_session = FakeSession()

    @asynccontextmanager
    async def fake_scope():
        yield fake_session

    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(return_value=FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[1]))
    monkeypatch.setattr("app.core.tasks.notify_worker.NotificationSettingsService.get_or_create", AsyncMock(return_value=DummySettings()))
    monkeypatch.setattr(
        "app.core.tasks.notify_worker.build_daily_digest",
        AsyncMock(return_value=SimpleNamespace(text="digest", series=[{"day": "2026-01-01", "revenue_net": 100}], kpi_summary={}, ops_summary={}, fx_summary={}, warnings=[])),
    )

    await worker.tick()
    assert bot.send_photo.await_count == 1
    assert bot.send_document.await_count == 0
    assert fake_session.committed is True


@pytest.mark.asyncio
async def test_digest_pdf_uses_document(monkeypatch):
    class DummySettings:
        fx_delta_enabled = False
        digest_enabled = True
        digest_tz = "UTC"
        digest_time_local = "00:00"
        digest_last_sent_at = None
        digest_format = "pdf"
        weekly_enabled = False
        weekly_tz = "UTC"
        weekly_time_local = "09:30"
        weekly_day_of_week = 0
        weekly_last_sent_at = None
        last_error_notice_at = None

    class FakeSession:
        async def commit(self):
            return None

    @asynccontextmanager
    async def fake_scope():
        yield FakeSession()

    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(return_value=FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[1]))
    monkeypatch.setattr("app.core.tasks.notify_worker.NotificationSettingsService.get_or_create", AsyncMock(return_value=DummySettings()))
    monkeypatch.setattr(
        "app.core.tasks.notify_worker.build_daily_digest",
        AsyncMock(return_value=SimpleNamespace(text="digest", series=[{"day": "2026-01-01", "revenue_net": 100}], kpi_summary={}, ops_summary={}, fx_summary={}, warnings=[])),
    )

    await worker.tick()
    assert bot.send_document.await_count == 1
