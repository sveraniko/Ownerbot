from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.schema import AdvicePayload, AdviceSuggestedTool, LLMIntent


class _DummyMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=99)
        self.answers = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_owner_console_advice_does_not_auto_run_tools(monkeypatch) -> None:
    from app.bot.routers import owner_console

    msg = _DummyMessage()
    called = {"run_tool": 0}

    async def _llm_plan_intent(**kwargs):
        return (
            LLMIntent(
                intent_kind="ADVICE",
                advice=AdvicePayload(
                    bullets=["Проверьте цену и трафик."],
                    experiments=["Сравнить 7д vs 30д."],
                    suggested_tools=[AdviceSuggestedTool(tool="kpi_snapshot", payload={})],
                ),
                confidence=0.7,
            ),
            "MOCK",
        )

    async def _run_tool(*args, **kwargs):
        called["run_tool"] += 1
        raise AssertionError("tool must not run automatically for ADVICE")

    async def _noop(*args, **kwargs):
        return None

    class _Redis:
        async def set(self, *args, **kwargs):
            return True

    monkeypatch.setattr(owner_console, "route_intent", lambda text: SimpleNamespace(tool=None, payload={}, presentation=None, error_message="Не понял"))
    monkeypatch.setattr(owner_console, "llm_plan_intent", _llm_plan_intent)
    monkeypatch.setattr(owner_console, "run_tool", _run_tool)
    async def _get_redis():
        return _Redis()

    monkeypatch.setattr(owner_console, "get_redis", _get_redis)
    monkeypatch.setattr(owner_console, "get_settings", lambda: SimpleNamespace(upstream_mode="DEMO", llm_provider="MOCK", llm_intent_enabled=True))
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)
    monkeypatch.setattr(owner_console, "write_retrospective_event", _noop)

    await owner_console.handle_tool_call(msg, "почему просели продажи")

    assert called["run_tool"] == 0
    assert msg.answers
    assert msg.answers[-1][0].startswith("🧭")
    assert "Гипотезы" in msg.answers[-1][0]
