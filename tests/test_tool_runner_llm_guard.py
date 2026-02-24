from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.services.tool_runner import run_tool
from app.tools.contracts import ToolActor, ToolTenant
from app.tools.registry_setup import build_registry


@pytest.mark.asyncio
async def test_llm_action_forces_dry_run(monkeypatch) -> None:
    registry = build_registry()
    called = {}

    async def _fake_handler(payload, correlation_id, session, **kwargs):
        called["dry_run"] = payload.dry_run
        return SimpleNamespace(status="ok", warnings=[], error=None)

    tool = registry.get("notify_team")
    monkeypatch.setattr(tool, "handler", _fake_handler)
    monkeypatch.setattr("app.bot.services.tool_runner.verify_response", lambda response: response)
    monkeypatch.setattr("app.bot.services.tool_runner.get_settings", lambda: SimpleNamespace(llm_allowed_action_tools=["notify_team"], upstream_mode="DEMO"))

    async def _session_factory():
        class _Ctx:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *args):
                return False

        return _Ctx()

    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *args):
            return False

    response = await run_tool(
        "notify_team",
        {"message": "hello", "dry_run": False},
        actor=ToolActor(owner_user_id=1),
        tenant=ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
        correlation_id="c1",
        registry=registry,
        session_factory=lambda: _Ctx(),
        intent_source="LLM",
    )

    assert response.status == "ok"
    assert called["dry_run"] is True


@pytest.mark.asyncio
async def test_llm_action_allowlist_blocks_tool(monkeypatch) -> None:
    registry = build_registry()
    monkeypatch.setattr("app.bot.services.tool_runner.get_settings", lambda: SimpleNamespace(llm_allowed_action_tools=[], upstream_mode="DEMO"))

    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *args):
            return False

    response = await run_tool(
        "notify_team",
        {"message": "hello"},
        actor=ToolActor(owner_user_id=1),
        tenant=ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
        correlation_id="c1",
        registry=registry,
        session_factory=lambda: _Ctx(),
        intent_source="LLM",
    )

    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ACTION_TOOL_NOT_ALLOWED"
