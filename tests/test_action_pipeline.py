from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.actions.confirm_flow import compute_payload_hash, create_confirm_token, get_confirm_payload
from app.actions.idempotency import claim_action, finalize_action
from app.core.redis import get_test_redis
from app.storage.models import Base, OwnerbotDemoOrder
from app.tools.contracts import ToolActor
from app.tools.impl.flag_order import Payload as FlagPayload, handle as flag_handle


@pytest.mark.asyncio
async def test_flag_order_dry_run_preview_ok():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add(
            OwnerbotDemoOrder(
                order_id="OB-1234",
                status="stuck",
                amount=123.45,
                currency="EUR",
                customer_id="cust_001",
                flagged=False,
            )
        )
        await session.commit()

    async with async_session() as session:
        payload = FlagPayload(order_id="OB-1234", reason="Suspicious", dry_run=True)
        response = await flag_handle(payload, "corr", session)

    assert response.status == "ok"
    assert response.data["dry_run"] is True
    assert response.data["will_update"]["order_id"] == "OB-1234"
    assert response.provenance.sources


@pytest.mark.asyncio
async def test_flag_order_commit_updates_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        session.add(
            OwnerbotDemoOrder(
                order_id="OB-5678",
                status="stuck",
                amount=200.00,
                currency="EUR",
                customer_id="cust_002",
                flagged=False,
            )
        )
        await session.commit()

    actor = ToolActor(owner_user_id=42)
    async with async_session() as session:
        payload = FlagPayload(order_id="OB-5678", reason="Test", dry_run=False)
        response = await flag_handle(payload, "corr", session, actor)

    assert response.status == "ok"
    async with async_session() as session:
        row = await session.get(OwnerbotDemoOrder, "OB-5678")
        assert row is not None
        assert row.flagged is True
        assert row.flag_reason == "Test"
        assert row.flagged_by == 42
        assert isinstance(row.flagged_at, datetime)


@pytest.mark.asyncio
async def test_confirm_flow_roundtrip(monkeypatch):
    async def _get_redis():
        return await get_test_redis()

    monkeypatch.setattr("app.actions.confirm_flow.get_redis", _get_redis)
    payload = {"tool_name": "flag_order", "payload_commit": {"order_id": "OB-1"}}
    token = await create_confirm_token(payload, ttl_seconds=60)
    stored = await get_confirm_payload(token)

    assert stored is not None
    assert stored["payload"]["tool_name"] == "flag_order"


@pytest.mark.asyncio
async def test_confirm_payload_hash_matches_compute(monkeypatch):
    async def _get_redis():
        return await get_test_redis()

    monkeypatch.setattr("app.actions.confirm_flow.get_redis", _get_redis)
    payload = {
        "tool_name": "flag_order",
        "payload_commit": {"order_id": "OB-1", "dry_run": False},
        "idempotency_key": "idem-1",
    }

    token = await create_confirm_token(payload, ttl_seconds=60)
    stored = await get_confirm_payload(token)

    assert stored is not None
    assert stored["payload_hash"] == compute_payload_hash(payload)


@pytest.mark.asyncio
async def test_claim_action_prevents_double_commit():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as first_session:
        created, claimed = await claim_action(
            first_session,
            idempotency_key="idem-1",
            tool="flag_order",
            payload_hash="hash",
            correlation_id="corr-1",
        )
        assert claimed is True
        assert created is not None
        assert created.status == "in_progress"

    async with async_session() as second_session:
        existing, claimed_again = await claim_action(
            second_session,
            idempotency_key="idem-1",
            tool="flag_order",
            payload_hash="hash",
            correlation_id="corr-2",
        )
        assert claimed_again is False
        assert existing is not None
        assert existing.status == "in_progress"

    async with async_session() as finalize_session:
        await finalize_action(
            finalize_session,
            idempotency_key="idem-1",
            status="committed",
            correlation_id="corr-final",
        )

    async with async_session() as third_session:
        existing_after_finalize, claimed_third = await claim_action(
            third_session,
            idempotency_key="idem-1",
            tool="flag_order",
            payload_hash="hash",
            correlation_id="corr-3",
        )
        assert claimed_third is False
        assert existing_after_finalize is not None
        assert existing_after_finalize.status == "committed"
