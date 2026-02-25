from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.time import utcnow
from app.retro.service import retro_gaps, retro_summary
from app.storage.models import Base, OwnerbotAuditEvent


@pytest.mark.asyncio
async def test_retro_summary_aggregates_windowed_events() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    now = utcnow()
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotAuditEvent(
                    event_type="llm_intent_planned",
                    correlation_id="c1",
                    occurred_at=now - timedelta(days=1),
                    payload_json=json.dumps({"intent_kind": "TOOL", "confidence": 0.7, "tool": "sis_fx_status"}),
                ),
                OwnerbotAuditEvent(
                    event_type="quality_assessment",
                    correlation_id="c2",
                    occurred_at=now - timedelta(days=1),
                    payload_json=json.dumps(
                        {
                            "intent_source": "LLM",
                            "intent_kind": "TOOL",
                            "confidence": "high",
                            "top_warning_codes": ["upstream_not_wired"],
                        }
                    ),
                ),
                OwnerbotAuditEvent(
                    event_type="quality_assessment",
                    correlation_id="c3",
                    occurred_at=now - timedelta(days=1),
                    payload_json=json.dumps(
                        {
                            "intent_source": "RULE",
                            "intent_kind": "ADVICE",
                            "confidence": "med",
                            "top_warning_codes": ["no_data"],
                        }
                    ),
                ),
                OwnerbotAuditEvent(
                    event_type="tool_call_started",
                    correlation_id="c4",
                    occurred_at=now - timedelta(days=2),
                    payload_json=json.dumps({"tool": "sis_fx_status"}),
                ),
                OwnerbotAuditEvent(
                    event_type="tool_call_finished",
                    correlation_id="c5",
                    occurred_at=now - timedelta(days=2),
                    payload_json=json.dumps({"tool": "sis_fx_status", "error_code": "UPSTREAM_NOT_IMPLEMENTED"}),
                ),
                OwnerbotAuditEvent(
                    event_type="agent_plan_previewed_v2",
                    correlation_id="c6",
                    occurred_at=now - timedelta(days=2),
                    payload_json="{}",
                ),
                OwnerbotAuditEvent(
                    event_type="agent_plan_committed_v2",
                    correlation_id="c7",
                    occurred_at=now - timedelta(days=2),
                    payload_json="{}",
                ),
                OwnerbotAuditEvent(
                    event_type="advice_memo_generated",
                    correlation_id="c8",
                    occurred_at=now - timedelta(days=2),
                    payload_json="{}",
                ),
                OwnerbotAuditEvent(
                    event_type="advice_data_brief_built",
                    correlation_id="c9",
                    occurred_at=now - timedelta(days=2),
                    payload_json="{}",
                ),
                OwnerbotAuditEvent(
                    event_type="llm_intent_failed",
                    correlation_id="c10",
                    occurred_at=now - timedelta(days=2),
                    payload_json=json.dumps({"error_class": "NO_TOOL"}),
                ),
                OwnerbotAuditEvent(
                    event_type="tool_call_started",
                    correlation_id="cold",
                    occurred_at=now - timedelta(days=40),
                    payload_json=json.dumps({"tool": "old"}),
                ),
            ]
        )
        await session.commit()

    async with async_session() as session:
        summary = await retro_summary(session, 7)

    assert summary.totals["tool_calls_total"] == 1
    assert summary.totals["plans_previewed_total"] == 1
    assert summary.totals["plans_committed_total"] == 1
    assert summary.totals["memos_generated_total"] == 1
    assert summary.totals["briefs_built_total"] == 1
    assert summary.routing["rule_hits_total"] == 1
    assert summary.routing["llm_plans_total"] == 1
    assert summary.quality["confidence_counts"]["TOOL"]["high"] == 1
    assert summary.quality["confidence_counts"]["ADVICE"]["med"] == 1
    assert summary.failures["unknown_total"] == 2


@pytest.mark.asyncio
async def test_retro_gaps_collects_tool_and_wizard_gaps() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    now = utcnow()
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotAuditEvent(
                    event_type="tool_call_finished",
                    correlation_id="g1",
                    occurred_at=now - timedelta(days=1),
                    payload_json=json.dumps({"tool": "sis_fx_reprice", "error_code": "UPSTREAM_NOT_IMPLEMENTED"}),
                ),
                OwnerbotAuditEvent(
                    event_type="tool_call_finished",
                    correlation_id="g2",
                    occurred_at=now - timedelta(days=1),
                    payload_json=json.dumps({"tool": "notify_team", "error_code": "ACTION_TOOL_NOT_ALLOWED"}),
                ),
                OwnerbotAuditEvent(
                    event_type="agent_action_wizard_started",
                    correlation_id="g3",
                    occurred_at=now - timedelta(days=1),
                    payload_json=json.dumps({"missing_fields": ["order_id", "reason"]}),
                ),
            ]
        )
        await session.commit()

    async with async_session() as session:
        gaps = await retro_gaps(session, 30)

    assert gaps.top_unimplemented_tools[0]["tool_name"] == "sis_fx_reprice"
    assert gaps.top_disallowed_actions[0]["tool_name"] == "notify_team"
    params = {item["param"] for item in gaps.top_missing_params}
    assert {"order_id", "reason"}.issubset(params)
