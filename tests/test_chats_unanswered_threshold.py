from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.time import utcnow
from app.storage.models import Base, OwnerbotDemoChatThread
from app.tools.impl.chats_unanswered import Payload, handle


@pytest.mark.asyncio
async def test_chats_unanswered_threshold_filters_hours() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = utcnow()
    async with session_factory() as session:
        session.add_all(
            [
                OwnerbotDemoChatThread(
                    thread_id="t1",
                    customer_id="c1",
                    open=True,
                    last_customer_message_at=now - timedelta(hours=1),
                    last_manager_reply_at=None,
                ),
                OwnerbotDemoChatThread(
                    thread_id="t2",
                    customer_id="c2",
                    open=True,
                    last_customer_message_at=now - timedelta(hours=3),
                    last_manager_reply_at=None,
                ),
                OwnerbotDemoChatThread(
                    thread_id="t3",
                    customer_id="c3",
                    open=True,
                    last_customer_message_at=now - timedelta(hours=7),
                    last_manager_reply_at=now - timedelta(hours=8),
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        r2 = await handle(Payload(threshold_hours=2, limit=20), "corr", session)
        r6 = await handle(Payload(threshold_hours=6, limit=20), "corr", session)

    assert r2.status == "ok"
    assert {x["thread_id"] for x in r2.data["threads"]} == {"t2", "t3"}
    assert {x["thread_id"] for x in r6.data["threads"]} == {"t3"}
