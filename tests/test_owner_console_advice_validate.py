from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


class _DummyMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=11)
        self.answers = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


class _DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=5)
        self.message = _DummyMessage()

    async def answer(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_validate_with_tools_runs_only_reports(monkeypatch) -> None:
    from app.bot.routers import owner_console
    from app.tools.contracts import ToolProvenance, ToolResponse

    token = "tok1"
    raw_payload = json.dumps(
        {
            "owner_user_id": 5,
            "suggested_tools": [
                {"tool": "kpi_snapshot", "payload": {}},
                {"tool": "create_coupon", "payload": {"dry_run": True}},
            ],
            "suggested_actions": [],
        }
    )

    class _Redis:
        async def get(self, key):
            return raw_payload if key.endswith(token) else None

    async def _get_redis():
        return _Redis()

    called = []

    async def _run_tool(tool_name, *args, **kwargs):
        called.append(tool_name)
        return ToolResponse.ok(correlation_id="c", data={"ok": True}, provenance=ToolProvenance(sources=["test"]))

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(owner_console, "get_redis", _get_redis)
    monkeypatch.setattr(owner_console, "run_tool", _run_tool)
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)

    cb = _DummyCallback(f"{owner_console._ADVICE_VALIDATE_PREFIX}{token}")
    await owner_console.run_advice_validation_tools(cb)

    assert called == ["kpi_snapshot"]


@pytest.mark.asyncio
async def test_suggested_action_preview_never_commits_without_confirm(monkeypatch) -> None:
    from app.bot.routers import owner_console
    from app.tools.contracts import ToolProvenance, ToolResponse

    token = "tok2"
    raw_payload = json.dumps(
        {
            "owner_user_id": 5,
            "suggested_tools": [],
            "suggested_actions": [
                {"label": "preview", "tool": "create_coupon", "payload_partial": {"percent_off": 10}, "why": "x"}
            ],
        }
    )

    class _Redis:
        async def get(self, key):
            return raw_payload if key.endswith(token) else None

    async def _get_redis():
        return _Redis()

    observed = {}

    async def _execute_plan_preview(plan, ctx):
        observed["dry_run"] = plan.steps[0].payload.get("dry_run")
        return SimpleNamespace(
            response=ToolResponse.ok(correlation_id="c", data={"dry_run": True}, provenance=ToolProvenance(sources=["test"])),
            preview_text="preview",
            confirm_needed=False,
            confirm_cb_data=None,
            confirm_only_main_cb_data=None,
            cancel_cb_data=None,
        )

    monkeypatch.setattr(owner_console, "get_redis", _get_redis)
    monkeypatch.setattr(owner_console, "execute_plan_preview", _execute_plan_preview)

    cb = _DummyCallback(f"{owner_console._ADVICE_ACTION_PREFIX}{token}")
    await owner_console.run_advice_action_preview(cb)

    assert observed["dry_run"] is True
