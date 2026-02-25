from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_actions.plan_builder import build_plan_from_text
from app.agent_actions.plan_executor import clear_active_plan, execute_plan_preview, get_active_plan
from app.agent_actions.plan_models import PlanIntent, PlanStep
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse, ToolTenant


class _Redis:
    def __init__(self) -> None:
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, nx=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.mark.asyncio
async def test_plan_builder_fx_with_notify() -> None:
    settings = SimpleNamespace()
    plan = build_plan_from_text("проверь курс и если надо обнови цены и сообщи команде", actor=None, settings=settings)
    assert plan is not None
    assert len(plan.steps) == 3
    assert plan.steps[0].tool_name == "sis_fx_status"
    assert plan.steps[1].tool_name == "sis_fx_reprice_auto"
    assert plan.steps[2].kind == "NOTIFY_TEAM"


@pytest.mark.asyncio
async def test_plan_builder_coupon_with_notify() -> None:
    settings = SimpleNamespace()
    plan = build_plan_from_text("купон -10% на сутки и пингани команду", actor=None, settings=settings)
    assert plan is not None
    assert plan.steps[0].tool_name == "create_coupon"
    assert len(plan.steps) == 2


@pytest.mark.asyncio
async def test_plan_preview_noop_without_confirm(monkeypatch) -> None:
    from app.agent_actions import plan_executor

    redis = _Redis()

    async def _get_redis():
        return redis

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(correlation_id="c", data={"status": "noop", "would_apply": False}, provenance=ToolProvenance(sources=["demo"]))

    async def _audit(*args, **kwargs):
        return None

    monkeypatch.setattr(plan_executor, "get_redis", _get_redis)
    monkeypatch.setattr(plan_executor, "run_tool", _run_tool)
    monkeypatch.setattr(plan_executor, "write_audit_event", _audit)

    plan = PlanIntent(
        plan_id="p1",
        source="RULE_PHRASE_PACK",
        steps=[PlanStep(step_id="s1", kind="TOOL", tool_name="sis_fx_reprice_auto", payload={"dry_run": True}, requires_confirm=True)],
        summary="fx",
    )
    result = await execute_plan_preview(
        plan,
        {
            "settings": SimpleNamespace(llm_allowed_action_tools=["sis_fx_reprice_auto"], upstream_mode="DEMO"),
            "correlation_id": "c",
            "actor": ToolActor(owner_user_id=1),
            "tenant": ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
            "chat_id": 42,
            "idempotency_key": "idem-1",
        },
    )
    assert result.confirm_needed is False


@pytest.mark.asyncio
async def test_plan_preview_would_apply_with_confirm(monkeypatch) -> None:
    from app.agent_actions import plan_executor

    redis = _Redis()

    async def _get_redis():
        return redis

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(correlation_id="c", data={"would_apply": True, "affected_count": 2}, provenance=ToolProvenance(sources=["demo"]))

    async def _audit(*args, **kwargs):
        return None

    seq = ["tok1", "tok2"]

    async def _token(payload):
        return seq.pop(0)

    monkeypatch.setattr(plan_executor, "get_redis", _get_redis)
    monkeypatch.setattr(plan_executor, "run_tool", _run_tool)
    monkeypatch.setattr(plan_executor, "write_audit_event", _audit)
    monkeypatch.setattr(plan_executor, "create_confirm_token", _token)

    plan = PlanIntent(
        plan_id="p2",
        source="RULE_PHRASE_PACK",
        steps=[PlanStep(step_id="s1", kind="TOOL", tool_name="sis_fx_reprice_auto", payload={"dry_run": True}, requires_confirm=True)],
        summary="fx",
    )
    result = await execute_plan_preview(
        plan,
        {
            "settings": SimpleNamespace(llm_allowed_action_tools=["sis_fx_reprice_auto"], upstream_mode="DEMO"),
            "correlation_id": "c",
            "actor": ToolActor(owner_user_id=1),
            "tenant": ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
            "chat_id": 42,
            "idempotency_key": "idem-1",
        },
    )
    assert result.confirm_needed is True
    assert result.confirm_cb_data == "confirm:tok1"
    assert result.confirm_only_main_cb_data == "confirm:tok2"


@pytest.mark.asyncio
async def test_plan_cancel_clear_state(monkeypatch) -> None:
    from app.agent_actions import plan_executor

    redis = _Redis()

    async def _get_redis():
        return redis

    monkeypatch.setattr(plan_executor, "get_redis", _get_redis)
    await plan_executor.set_active_plan(10, {"plan": {"plan_id": "x"}})
    assert await get_active_plan(10) is not None
    await clear_active_plan(10)
    assert await get_active_plan(10) is None
