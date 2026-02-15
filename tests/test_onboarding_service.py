from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.onboarding.service import OnboardContext, build_onboard_checklist
from app.storage.models import Base


@pytest.mark.asyncio
async def test_build_onboard_checklist_warn_when_notifications_and_team_missing(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _caps(*, settings, correlation_id, force_refresh=False):
        return {"checked_at": "2026-01-01T00:00:00+00:00", "capabilities": {"fx": {"status": "supported", "supported": True}}}

    monkeypatch.setattr("app.onboarding.service.get_sis_capabilities", _caps)

    async with async_session() as session:
        settings = SimpleNamespace(
            upstream_mode="DEMO",
            sis_base_url="",
            sis_ownerbot_api_key="",
            manager_chat_ids=[],
            bot_token="token",
            owner_ids=[1],
            asr_provider="mock",
            llm_provider="OFF",
            openai_api_key=None,
            asr_convert_voice_ogg_to_wav=False,
            sizebot_check_enabled=False,
            sizebot_base_url="",
            sizebot_api_key="",
            upstream_runtime_toggle_enabled=False,
            upstream_redis_key="ownerbot:upstream_mode",
        )
        result = await build_onboard_checklist(OnboardContext(settings=settings, session=session, owner_id=1, correlation_id="cid"))

    assert result["status"] == "warn"
    assert any(item["key"] == "notifications" and item["status"] == "warn" for item in result["items"])
    assert any(item["key"] == "team_routing" and item["status"] == "warn" for item in result["items"])


@pytest.mark.asyncio
async def test_build_onboard_checklist_fail_when_all_capabilities_unsupported(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _caps(*, settings, correlation_id, force_refresh=False):
        return {
            "checked_at": "2026-01-01T00:00:00+00:00",
            "capabilities": {
                "fx": {"status": "unsupported", "supported": False},
                "discounts": {"status": "unsupported", "supported": False},
            },
        }

    monkeypatch.setattr("app.onboarding.service.get_sis_capabilities", _caps)

    async with async_session() as session:
        settings = SimpleNamespace(
            upstream_mode="SIS_HTTP",
            sis_base_url="http://sis",
            sis_ownerbot_api_key="k",
            manager_chat_ids=[100],
            bot_token="token",
            owner_ids=[1],
            asr_provider="mock",
            llm_provider="OFF",
            openai_api_key=None,
            asr_convert_voice_ogg_to_wav=False,
            sizebot_check_enabled=False,
            sizebot_base_url="",
            sizebot_api_key="",
            upstream_runtime_toggle_enabled=False,
            upstream_redis_key="ownerbot:upstream_mode",
        )
        result = await build_onboard_checklist(OnboardContext(settings=settings, session=session, owner_id=1, correlation_id="cid"))

    assert result["status"] == "fail"
    assert any(item["key"] == "capabilities" and item["status"] == "fail" for item in result["items"])
