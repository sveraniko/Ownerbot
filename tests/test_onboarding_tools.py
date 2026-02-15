from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Base, OwnerNotifySettings
from app.tools.impl import onboard_apply_preset, onboard_test_run


class _FakeRedis:
    def __init__(self, *, cooldown: bool = False, lock_acquired: bool = True) -> None:
        self._cooldown = cooldown
        self._lock_acquired = lock_acquired
        self._values: dict[str, str] = {}

    async def get(self, key: str):
        if "cooldown" in key and self._cooldown:
            return "1"
        return self._values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx:
            if not self._lock_acquired:
                return False
            self._values[key] = value
            return True
        self._values[key] = value
        return True

    async def delete(self, key: str):
        self._values.pop(key, None)


@pytest.mark.asyncio
async def test_onboard_apply_preset_dry_run_has_diffs() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        actor = SimpleNamespace(owner_user_id=100)
        res = await onboard_apply_preset.handle(onboard_apply_preset.Payload(preset="standard", dry_run=True), "cid", session, actor=actor)

    assert res.status == "ok"
    assert res.data["dry_run"] is True
    assert res.data["changes_count"] > 0


@pytest.mark.asyncio
async def test_onboard_apply_preset_commit_updates_db() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        actor = SimpleNamespace(owner_user_id=101)
        res = await onboard_apply_preset.handle(onboard_apply_preset.Payload(preset="minimal", dry_run=False), "cid2", session, actor=actor)
        assert res.status == "ok"
        row = await session.get(OwnerNotifySettings, 101)

    assert row is not None
    assert row.weekly_enabled is True
    assert row.fx_apply_events_enabled is True
    assert row.onboard_completed_at is not None
    assert row.onboard_last_status == "ok"


@pytest.mark.asyncio
async def test_onboard_test_run_respects_cooldown(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _redis():
        return _FakeRedis(cooldown=True)

    monkeypatch.setattr(onboard_test_run, "get_redis", _redis)

    async with async_session() as session:
        actor = SimpleNamespace(owner_user_id=102)
        res = await onboard_test_run.handle(onboard_test_run.Payload(), "cid3", session, actor=actor)

    assert res.status == "ok"
    assert "cooldown" in str(res.data.get("message", "")).lower()
