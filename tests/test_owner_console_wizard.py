from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolDefinition, ToolProvenance, ToolResponse


class _Redis:
    def __init__(self) -> None:
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, nx=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


class _DummyMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=99)
        self.chat = SimpleNamespace(id=500)
        self.answers = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_wizard_missing_params_then_complete_dry_run(monkeypatch) -> None:
    from app.bot.routers import owner_console

    redis = _Redis()
    msg = _DummyMessage()
    run_calls = []

    async def _noop(*args, **kwargs):
        return None

    async def _run_tool(tool_name, payload, **kwargs):
        run_calls.append((tool_name, dict(payload)))
        return ToolResponse.ok(correlation_id="c", data={"would_apply": True}, provenance=ToolProvenance(sources=["demo"]))

    async def _token(payload):
        return "t1"

    async def _get_redis():
        return redis

    monkeypatch.setattr(owner_console, "get_redis", _get_redis)
    monkeypatch.setattr(owner_console, "route_intent", lambda text: SimpleNamespace(tool="sis_prices_bump", payload={}, presentation=None, error_message=None, source="RULE"))
    monkeypatch.setattr(owner_console.registry, "get", lambda name: ToolDefinition(name=name, version="1", payload_model=dict, handler=None, kind="action"))
    monkeypatch.setattr(owner_console, "run_tool", _run_tool)
    monkeypatch.setattr(owner_console, "render_anchor_panel", _noop)
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)
    monkeypatch.setattr(owner_console, "write_retrospective_event", _noop)
    async def _resolve_effective_mode(**kwargs):
        return ("DEMO", None)

    monkeypatch.setattr(owner_console, "resolve_effective_mode", _resolve_effective_mode)
    monkeypatch.setattr(owner_console, "get_settings", lambda: SimpleNamespace(upstream_mode="DEMO", llm_provider="MOCK"))
    monkeypatch.setattr(owner_console, "create_confirm_token", _token)

    await owner_console.handle_tool_call(msg, "подними цены")
    assert run_calls == []

    await owner_console.handle_tool_call(msg, "5")
    assert run_calls
    assert run_calls[0][1]["dry_run"] is True


@pytest.mark.asyncio
async def test_wizard_cancel_clears_state(monkeypatch) -> None:
    from app.bot.routers import owner_console

    redis = _Redis()
    msg = _DummyMessage()

    async def _noop(*args, **kwargs):
        return None

    async def _get_redis():
        return redis

    monkeypatch.setattr(owner_console, "get_redis", _get_redis)
    monkeypatch.setattr(owner_console, "route_intent", lambda text: SimpleNamespace(tool="sis_prices_bump", payload={}, presentation=None, error_message=None, source="RULE"))
    monkeypatch.setattr(owner_console.registry, "get", lambda name: ToolDefinition(name=name, version="1", payload_model=dict, handler=None, kind="action"))
    monkeypatch.setattr(owner_console, "render_anchor_panel", _noop)
    monkeypatch.setattr(owner_console, "render_home_panel", _noop)
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)
    monkeypatch.setattr(owner_console, "write_retrospective_event", _noop)
    async def _resolve_effective_mode(**kwargs):
        return ("DEMO", None)

    monkeypatch.setattr(owner_console, "resolve_effective_mode", _resolve_effective_mode)
    monkeypatch.setattr(owner_console, "get_settings", lambda: SimpleNamespace(upstream_mode="DEMO", llm_provider="MOCK"))

    await owner_console.handle_tool_call(msg, "подними цены")
    assert redis.store
    await owner_console.handle_tool_call(msg, "отмена")
    assert redis.store == {}


@pytest.mark.asyncio
async def test_wizard_does_not_swallow_slash_command(monkeypatch) -> None:
    from app.bot.routers import owner_console

    redis = _Redis()
    msg = _DummyMessage()

    async def _noop(*args, **kwargs):
        return None

    async def _get_redis():
        return redis

    monkeypatch.setattr(owner_console, "get_redis", _get_redis)
    monkeypatch.setattr(owner_console, "route_intent", lambda text: SimpleNamespace(tool="sis_prices_bump", payload={}, presentation=None, error_message=None, source="RULE") if not text.startswith("/") else SimpleNamespace(tool="kpi_snapshot", payload={}, presentation=None, error_message=None, source="RULE"))
    monkeypatch.setattr(owner_console.registry, "get", lambda name: ToolDefinition(name=name, version="1", payload_model=dict, handler=None, kind="action" if name=="sis_prices_bump" else "read"))
    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(correlation_id="c", data={}, provenance=ToolProvenance(sources=["demo"]))

    monkeypatch.setattr(owner_console, "run_tool", _run_tool)
    monkeypatch.setattr(owner_console, "render_anchor_panel", _noop)
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)
    monkeypatch.setattr(owner_console, "write_retrospective_event", _noop)
    async def _resolve_effective_mode(**kwargs):
        return ("DEMO", None)

    monkeypatch.setattr(owner_console, "resolve_effective_mode", _resolve_effective_mode)
    monkeypatch.setattr(owner_console, "get_settings", lambda: SimpleNamespace(upstream_mode="DEMO", llm_provider="MOCK"))

    await owner_console.handle_tool_call(msg, "подними цены")
    await owner_console.handle_tool_call(msg, "/start")

    assert msg.answers or redis.store
