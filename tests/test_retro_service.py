from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.time import utcnow
from app.retro.service import retro_funnels, retro_gaps, retro_gaps_with_deltas, retro_summary, retro_summary_with_deltas
from app.storage.models import Base, OwnerbotAuditEvent


async def _session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_retro_summary_aggregates_windowed_events() -> None:
    async_session = await _session_factory()
    now = utcnow()
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotAuditEvent(event_type="llm_intent_planned", correlation_id="c1", occurred_at=now - timedelta(days=1), payload_json=json.dumps({"tool": "sis_fx_status"})),
                OwnerbotAuditEvent(
                    event_type="quality_assessment",
                    correlation_id="c2",
                    occurred_at=now - timedelta(days=1),
                    payload_json=json.dumps({"intent_source": "LLM", "intent_kind": "TOOL", "confidence": "high", "top_warning_codes": ["upstream_not_wired"]}),
                ),
                OwnerbotAuditEvent(
                    event_type="quality_assessment",
                    correlation_id="c3",
                    occurred_at=now - timedelta(days=1),
                    payload_json=json.dumps({"intent_source": "RULE", "intent_kind": "ADVICE", "confidence": "med", "top_warning_codes": ["no_data"]}),
                ),
                OwnerbotAuditEvent(event_type="tool_call_started", correlation_id="c4", occurred_at=now - timedelta(days=2), payload_json=json.dumps({"tool": "sis_fx_status"})),
                OwnerbotAuditEvent(event_type="tool_call_finished", correlation_id="c5", occurred_at=now - timedelta(days=2), payload_json=json.dumps({"tool": "sis_fx_status", "error_code": "UPSTREAM_NOT_IMPLEMENTED"})),
                OwnerbotAuditEvent(event_type="agent_plan_previewed_v2", correlation_id="c6", occurred_at=now - timedelta(days=2), payload_json="{}"),
                OwnerbotAuditEvent(event_type="agent_plan_committed_v2", correlation_id="c7", occurred_at=now - timedelta(days=2), payload_json="{}"),
                OwnerbotAuditEvent(event_type="advice_memo_generated", correlation_id="c8", occurred_at=now - timedelta(days=2), payload_json="{}"),
                OwnerbotAuditEvent(event_type="advice_data_brief_built", correlation_id="c9", occurred_at=now - timedelta(days=2), payload_json="{}"),
                OwnerbotAuditEvent(event_type="llm_intent_failed", correlation_id="c10", occurred_at=now - timedelta(days=2), payload_json=json.dumps({"error_class": "NO_TOOL"})),
                OwnerbotAuditEvent(event_type="tool_call_started", correlation_id="cold", occurred_at=now - timedelta(days=40), payload_json=json.dumps({"tool": "old"})),
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
    async_session = await _session_factory()
    now = utcnow()
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotAuditEvent(event_type="tool_call_finished", correlation_id="g1", occurred_at=now - timedelta(days=1), payload_json=json.dumps({"tool": "sis_fx_reprice", "error_code": "UPSTREAM_NOT_IMPLEMENTED"})),
                OwnerbotAuditEvent(event_type="tool_call_finished", correlation_id="g2", occurred_at=now - timedelta(days=1), payload_json=json.dumps({"tool": "notify_team", "error_code": "ACTION_TOOL_NOT_ALLOWED"})),
                OwnerbotAuditEvent(event_type="agent_action_wizard_started", correlation_id="g3", occurred_at=now - timedelta(days=1), payload_json=json.dumps({"missing_fields": ["order_id", "reason"]})),
            ]
        )
        await session.commit()

    async with async_session() as session:
        gaps = await retro_gaps(session, 30)

    assert gaps.top_unimplemented_tools[0]["tool_name"] == "sis_fx_reprice"
    assert gaps.top_disallowed_actions[0]["tool_name"] == "notify_team"
    params = {item["param"] for item in gaps.top_missing_params}
    assert {"order_id", "reason"}.issubset(params)


@pytest.mark.asyncio
async def test_retro_deltas() -> None:
    async_session = await _session_factory()
    now = utcnow()
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotAuditEvent(event_type="tool_call_started", correlation_id="p1", occurred_at=now - timedelta(days=12), payload_json=json.dumps({"tool": "sis_fx_status"})),
                OwnerbotAuditEvent(event_type="agent_plan_committed_v2", correlation_id="p2", occurred_at=now - timedelta(days=12), payload_json="{}"),
                OwnerbotAuditEvent(event_type="llm_intent_failed", correlation_id="p3", occurred_at=now - timedelta(days=12), payload_json=json.dumps({"error_class": "NO_TOOL"})),
                OwnerbotAuditEvent(event_type="tool_call_started", correlation_id="c1", occurred_at=now - timedelta(days=2), payload_json=json.dumps({"tool": "sis_fx_status"})),
                OwnerbotAuditEvent(event_type="tool_call_started", correlation_id="c2", occurred_at=now - timedelta(days=2), payload_json=json.dumps({"tool": "retro_summary"})),
                OwnerbotAuditEvent(event_type="agent_plan_committed_v2", correlation_id="c3", occurred_at=now - timedelta(days=2), payload_json="{}"),
                OwnerbotAuditEvent(event_type="agent_plan_committed_v2", correlation_id="c4", occurred_at=now - timedelta(days=2), payload_json="{}"),
            ]
        )
        await session.commit()

    async with async_session() as session:
        summary_report = await retro_summary_with_deltas(session, 7)
        gaps_report = await retro_gaps_with_deltas(session, 7)

    assert summary_report.deltas["tool_calls_total_delta"]["absolute"] == 1
    assert summary_report.deltas["plans_committed_delta"]["absolute"] == 1
    assert summary_report.deltas["unknown_total_delta"]["absolute"] == -1
    assert isinstance(gaps_report.deltas["top_unimplemented_tools_delta"], list)


@pytest.mark.asyncio
async def test_retro_funnels() -> None:
    async_session = await _session_factory()
    now = utcnow()
    async with async_session() as session:
        session.add_all(
            [
                OwnerbotAuditEvent(event_type="agent_plan_built", correlation_id="plan-1", occurred_at=now - timedelta(days=1), payload_json="{}"),
                OwnerbotAuditEvent(event_type="agent_plan_previewed_v2", correlation_id="plan-1", occurred_at=now - timedelta(days=1), payload_json="{}"),
                OwnerbotAuditEvent(event_type="agent_plan_committed_v2", correlation_id="plan-1", occurred_at=now - timedelta(days=1), payload_json="{}"),
                OwnerbotAuditEvent(event_type="agent_plan_built", correlation_id="plan-2", occurred_at=now - timedelta(days=1), payload_json="{}"),
                OwnerbotAuditEvent(event_type="agent_plan_cancelled", correlation_id="plan-2", occurred_at=now - timedelta(days=1), payload_json="{}"),
                OwnerbotAuditEvent(event_type="advice_data_brief_built", correlation_id="adv-1", occurred_at=now - timedelta(days=1), payload_json="{}"),
                OwnerbotAuditEvent(event_type="advice_playbook_used", correlation_id="adv-1", occurred_at=now - timedelta(days=1), payload_json="{}"),
                OwnerbotAuditEvent(event_type="advice_memo_generated", correlation_id="adv-1", occurred_at=now - timedelta(days=1), payload_json="{}"),
            ]
        )
        await session.commit()

    async with async_session() as session:
        report = await retro_funnels(session, 7)

    assert report.plan["built"] == 2
    assert report.plan["previewed"] == 1
    assert report.plan["committed"] == 1
    assert report.plan["cancelled"] == 1
    assert report.plan["rates"]["preview_per_built"] == 0.5
    assert report.advice["memo"] == 1
    assert report.advice["rates"]["memo_per_advice"] == 1.0
