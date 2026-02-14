from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolDefinition, ToolProvenance, ToolResponse, ToolWarning


class _DummyMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=99)
        self.answers = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_owner_console_action_dry_run_shows_force_button(monkeypatch) -> None:
    from app.bot.routers import owner_console
    from app.tools.impl.sis_prices_bump import Payload as BumpPayload

    msg = _DummyMessage()

    intent = SimpleNamespace(tool="sis_prices_bump", payload={"bump_percent": "10", "dry_run": True}, presentation=None, error_message=None)

    def _get(tool_name):
        return ToolDefinition(name=tool_name, version="1.0", payload_model=BumpPayload, handler=None, kind="action")

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(
            correlation_id="corr",
            data={"affected_count": 1},
            provenance=ToolProvenance(sources=["sis"]),
            warnings=[ToolWarning(code="MASS_CHANGE_OVER_10", message="Mass change")],
        )

    async def _noop(*args, **kwargs):
        return None

    tokens = ["tok-normal", "tok-force"]

    async def _create_token(payload):
        return tokens.pop(0)

    monkeypatch.setattr(owner_console, "route_intent", lambda text: intent)
    monkeypatch.setattr(owner_console.registry, "get", _get)
    monkeypatch.setattr(owner_console, "run_tool", _run_tool)
    monkeypatch.setattr(owner_console, "get_settings", lambda: SimpleNamespace(upstream_mode="DEMO", llm_intent_enabled=False))
    monkeypatch.setattr(owner_console, "get_redis", _noop)
    async def _resolve(**kwargs):
        return "DEMO", None

    monkeypatch.setattr(owner_console, "resolve_effective_mode", _resolve)
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)
    monkeypatch.setattr(owner_console, "write_retrospective_event", _noop)
    monkeypatch.setattr(owner_console, "create_confirm_token", _create_token)

    await owner_console.handle_tool_call(msg, "подними цены на 10")

    assert msg.answers
    _, markup = msg.answers[-1]
    flat = [b.text for row in markup.inline_keyboard for b in row]
    assert "⚠️ Применить несмотря на аномалию" in flat
