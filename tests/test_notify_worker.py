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
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
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
        fx_apply_events_enabled = False
        digest_enabled = True
        digest_include_fx = True
        digest_include_ops = False
        digest_tz = "UTC"
        digest_time_local = "00:00"
        digest_last_sent_at = None
        digest_format = "png"
        weekly_enabled = False
        ops_alerts_enabled = False
        ops_alerts_last_error_notice_at = None
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
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
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
        fx_apply_events_enabled = False
        digest_enabled = True
        digest_include_fx = True
        digest_include_ops = False
        digest_tz = "UTC"
        digest_time_local = "00:00"
        digest_last_sent_at = None
        digest_format = "pdf"
        weekly_enabled = False
        ops_alerts_enabled = False
        ops_alerts_last_error_notice_at = None
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
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[1]))
    monkeypatch.setattr("app.core.tasks.notify_worker.NotificationSettingsService.get_or_create", AsyncMock(return_value=DummySettings()))
    monkeypatch.setattr(
        "app.core.tasks.notify_worker.build_daily_digest",
        AsyncMock(return_value=SimpleNamespace(text="digest", series=[{"day": "2026-01-01", "revenue_net": 100}], kpi_summary={}, ops_summary={}, fx_summary={}, warnings=[])),
    )

    await worker.tick()
    assert bot.send_document.await_count == 1


@pytest.mark.asyncio
async def test_fx_apply_event_sent_once_and_state_updated(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        session.add(
            OwnerNotifySettings(
                owner_id=9,
                fx_apply_events_enabled=True,
                fx_apply_notify_failed=True,
                fx_apply_events_cooldown_hours=6,
            )
        )
        await session.commit()

    @asynccontextmanager
    async def fake_scope():
        async with async_session() as s:
            yield s

    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    response = SimpleNamespace(
        status="ok",
        data={"last_apply": {"at": "2025-01-02T10:00:00+00:00", "result": "failed", "error": "boom", "affected_count": 0}},
    )

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[9], upstream_mode="DEMO"))
    monkeypatch.setattr("app.core.tasks.notify_worker.sis_fx_status.handle", AsyncMock(return_value=response))

    await worker.tick()
    await worker.tick()

    assert bot.send_message.await_count == 1
    async with async_session() as session:
        row = await session.get(OwnerNotifySettings, 9)
        assert row.fx_apply_last_seen_key is not None
        assert row.fx_apply_last_sent_at is not None


@pytest.mark.asyncio
async def test_fx_apply_event_send_failure_does_not_update_state(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        session.add(OwnerNotifySettings(owner_id=10, fx_apply_events_enabled=True, fx_apply_notify_failed=True))
        await session.commit()

    @asynccontextmanager
    async def fake_scope():
        async with async_session() as s:
            yield s

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("boom")), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    response = SimpleNamespace(
        status="ok",
        data={"last_apply": {"at": "2025-01-02T10:00:00+00:00", "result": "failed", "error": "bad", "affected_count": 0}},
    )

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[10], upstream_mode="DEMO"))
    monkeypatch.setattr("app.core.tasks.notify_worker.sis_fx_status.handle", AsyncMock(return_value=response))

    await worker.tick()

    async with async_session() as session:
        row = await session.get(OwnerNotifySettings, 10)
        assert row.fx_apply_last_seen_key is None
        assert row.fx_apply_last_sent_at is None


@pytest.mark.asyncio
async def test_fx_apply_event_result_defaults(monkeypatch):
    class DummySettings:
        fx_delta_enabled = False
        fx_apply_events_enabled = True
        fx_apply_notify_applied = False
        fx_apply_notify_noop = False
        fx_apply_notify_failed = True
        fx_apply_events_cooldown_hours = 6
        fx_apply_last_seen_key = None
        fx_apply_last_sent_at = None
        fx_apply_last_error_notice_at = None
        digest_enabled = False
        digest_tz = "UTC"
        digest_include_fx = True
        digest_include_ops = False
        weekly_enabled = False
        ops_alerts_enabled = False
        ops_alerts_last_error_notice_at = None
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

    noop_response = SimpleNamespace(status="ok", data={"last_apply": {"at": "2025-01-02T10:00:00+00:00", "result": "noop", "reason": "cooldown"}})

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[1], upstream_mode="DEMO"))
    monkeypatch.setattr("app.core.tasks.notify_worker.NotificationSettingsService.get_or_create", AsyncMock(return_value=DummySettings()))
    monkeypatch.setattr("app.core.tasks.notify_worker.sis_fx_status.handle", AsyncMock(return_value=noop_response))

    await worker.tick()
    assert bot.send_message.await_count == 0

    failed_response = SimpleNamespace(status="ok", data={"last_apply": {"at": "2025-01-02T11:00:00+00:00", "result": "failed", "error": "err"}})
    monkeypatch.setattr("app.core.tasks.notify_worker.sis_fx_status.handle", AsyncMock(return_value=failed_response))
    await worker.tick()
    assert bot.send_message.await_count == 1


@pytest.mark.asyncio
async def test_ops_alert_sent_once_and_state_updated(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        session.add(OwnerNotifySettings(owner_id=11, ops_alerts_enabled=True, ops_alerts_cooldown_hours=6, digest_enabled=False))
        await session.commit()

    @asynccontextmanager
    async def fake_scope():
        async with async_session() as s:
            yield s

    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    snapshot = {
        "unanswered_chats": {"count": 2, "top": [{"thread_id": "t1"}], "threshold_hours": 2},
        "stuck_orders": {"count": 1, "top": [{"order_id": "o1"}]},
        "payment_issues": {"count": 1, "top": [{"order_id": "o2"}]},
        "errors": {"count": 1, "top": [{"id": 1}], "window_hours": 24},
        "inventory": {"out_of_stock": 1, "low_stock": 3, "top_out": [{"product_id": "p1"}], "top_low": [{"product_id": "p2"}]},
        "warnings": [],
    }

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[11]))
    monkeypatch.setattr("app.core.tasks.notify_worker.build_ops_snapshot", AsyncMock(return_value=snapshot))

    await worker.tick()
    await worker.tick()

    assert bot.send_message.await_count == 1
    async with async_session() as session:
        row = await session.get(OwnerNotifySettings, 11)
        assert row.ops_alerts_last_seen_key is not None
        assert row.ops_alerts_last_sent_at is not None


@pytest.mark.asyncio
async def test_ops_alert_send_failure_does_not_update_state(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        session.add(OwnerNotifySettings(owner_id=12, ops_alerts_enabled=True, digest_enabled=False))
        await session.commit()

    @asynccontextmanager
    async def fake_scope():
        async with async_session() as s:
            yield s

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("boom")), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    snapshot = {
        "unanswered_chats": {"count": 2, "top": [], "threshold_hours": 2},
        "stuck_orders": {"count": 0, "top": []},
        "payment_issues": {"count": 0, "top": []},
        "errors": {"count": 0, "top": [], "window_hours": 24},
        "inventory": {"out_of_stock": 0, "low_stock": 0, "top_out": [], "top_low": []},
        "warnings": [],
    }

    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[12]))
    monkeypatch.setattr("app.core.tasks.notify_worker.build_ops_snapshot", AsyncMock(return_value=snapshot))

    await worker.tick()

    async with async_session() as session:
        row = await session.get(OwnerNotifySettings, 12)
        assert row.ops_alerts_last_seen_key is None
        assert row.ops_alerts_last_sent_at is None


@pytest.mark.asyncio
async def test_ops_tool_warning_throttled(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        session.add(OwnerNotifySettings(owner_id=13, ops_alerts_enabled=True, digest_enabled=False))
        await session.commit()

    @asynccontextmanager
    async def fake_scope():
        async with async_session() as s:
            yield s

    bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock(), send_document=AsyncMock())
    worker = NotifyWorker(bot)

    snapshot = {
        "unanswered_chats": {"count": 0, "top": [], "threshold_hours": 2},
        "stuck_orders": {"count": 0, "top": []},
        "payment_issues": {"count": 0, "top": []},
        "errors": {"count": 0, "top": [], "window_hours": 24},
        "inventory": {"out_of_stock": 0, "low_stock": 0, "top_out": [], "top_low": []},
        "warnings": ["orders_search(stuck):UPSTREAM_NOT_IMPLEMENTED"],
    }

    audit_mock = AsyncMock()
    monkeypatch.setattr("app.core.tasks.notify_worker.write_audit_event", audit_mock)
    monkeypatch.setattr("app.core.tasks.notify_worker.session_scope", fake_scope)
    monkeypatch.setattr("app.core.tasks.notify_worker.get_redis", AsyncMock(side_effect=lambda: FakeRedis(lock=True)))
    monkeypatch.setattr("app.core.tasks.notify_worker.get_settings", lambda: SimpleNamespace(owner_ids=[13]))
    monkeypatch.setattr("app.core.tasks.notify_worker.build_ops_snapshot", AsyncMock(return_value=snapshot))

    await worker.tick()
    await worker.tick()

    calls = [c.args[0] for c in audit_mock.await_args_list if c.args]
    assert calls.count("notify_ops_alert_tool_failed") == 1
    assert bot.send_message.await_count == 0
