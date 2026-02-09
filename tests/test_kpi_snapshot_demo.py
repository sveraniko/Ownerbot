from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.storage.models import Base, OwnerbotDemoKpiDaily
from app.tools.impl.kpi_snapshot import KpiSnapshotPayload, handle


@pytest.mark.asyncio
async def test_kpi_snapshot_demo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add(
            OwnerbotDemoKpiDaily(
                day=date(2024, 1, 1),
                revenue_gross=100.0,
                revenue_net=90.0,
                orders_paid=5,
                orders_created=7,
                aov=20.0,
            )
        )
        await session.commit()

    async with async_session() as session:
        payload = KpiSnapshotPayload(day=date(2024, 1, 1))
        response = await handle(payload, "corr", session)

    assert response.status == "ok"
    assert response.data["revenue_gross"] == 100.0
    assert response.provenance.sources
