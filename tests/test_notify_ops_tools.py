from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.tools.impl import (
    ntf_ops_alerts_subscribe,
    ntf_ops_alerts_unsubscribe,
    ntf_status,
    ntf_escalation_enable,
    ntf_escalation_disable,
    ntf_escalation_ack,
    ntf_escalation_snooze,
)
from app.storage.models import Base, OwnerNotifySettings


@pytest.mark.asyncio
async def test_ops_alerts_subscribe_and_unsubscribe() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        actor = SimpleNamespace(owner_user_id=100)
        res = await ntf_ops_alerts_subscribe.handle(ntf_ops_alerts_subscribe.Payload(), "cid", session, actor=actor)
        assert res.status == "ok"

        row = await session.get(OwnerNotifySettings, 100)
        assert row is not None and row.ops_alerts_enabled is True

        res2 = await ntf_ops_alerts_unsubscribe.handle(ntf_ops_alerts_unsubscribe.Payload(), "cid2", session, actor=actor)
        assert res2.status == "ok"
        row2 = await session.get(OwnerNotifySettings, 100)
        assert row2 is not None and row2.ops_alerts_enabled is False


@pytest.mark.asyncio
async def test_ntf_status_contains_ops_alerts_fields() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        session.add(OwnerNotifySettings(owner_id=200, ops_alerts_enabled=True, ops_alerts_cooldown_hours=8))
        await session.commit()

        actor = SimpleNamespace(owner_user_id=200)
        res = await ntf_status.handle(ntf_status.Payload(), "cid", session, actor=actor)
        assert res.status == "ok"
        assert res.data["ops_alerts_enabled"] is True
        assert res.data["ops_alerts_cooldown_hours"] == 8


@pytest.mark.asyncio
async def test_escalation_tools_and_status() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        actor = SimpleNamespace(owner_user_id=210)
        await ntf_escalation_enable.handle(ntf_escalation_enable.Payload(), "cid1", session, actor=actor)
        row = await session.get(OwnerNotifySettings, 210)
        assert row is not None and row.escalation_enabled is True

        row.escalation_last_event_key = "ev-1"
        await session.commit()
        ack_res = await ntf_escalation_ack.handle(ntf_escalation_ack.Payload(), "cid2", session, actor=actor)
        assert ack_res.status == "ok"

        snooze_res = await ntf_escalation_snooze.handle(ntf_escalation_snooze.Payload(hours=12), "cid3", session, actor=actor)
        assert snooze_res.status == "ok"

        status_res = await ntf_status.handle(ntf_status.Payload(), "cid4", session, actor=actor)
        assert status_res.status == "ok"
        assert status_res.data["escalation_enabled"] is True

        off_res = await ntf_escalation_disable.handle(ntf_escalation_disable.Payload(), "cid5", session, actor=actor)
        assert off_res.status == "ok"
