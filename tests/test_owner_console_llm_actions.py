from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.schema import LLMIntent
from app.tools.contracts import ToolDefinition, ToolProvenance, ToolResponse


class _DummyMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=99)
        self.answers = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_llm_missing_parameter_returns_unknown_without_tool_call(monkeypatch) -> None:
    from app.bot.routers import owner_console
    from app.tools.impl.sis_prices_bump import Payload as BumpPayload

    msg = _DummyMessage()
    calls = {"run_tool": 0}

    async def _llm_plan_intent(**kwargs):
        return LLMIntent(intent_kind="TOOL", tool="sis_prices_bump", payload={}, confidence=0.8), "MOCK"

    async def _run_tool(*args, **kwargs):
        calls["run_tool"] += 1
        return ToolResponse.ok(correlation_id="c", data={}, provenance=ToolProvenance(sources=["demo"]))

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(owner_console, "route_intent", lambda text: SimpleNamespace(tool=None, payload={}, presentation=None, error_message="Не понял"))
    monkeypatch.setattr(owner_console, "llm_plan_intent", _llm_plan_intent)
    monkeypatch.setattr(owner_console.registry, "get", lambda name: ToolDefinition(name=name, version="1", payload_model=BumpPayload, handler=None, kind="action"))
    monkeypatch.setattr(owner_console, "run_tool", _run_tool)
    monkeypatch.setattr(owner_console, "get_settings", lambda: SimpleNamespace(upstream_mode="DEMO", llm_provider="MOCK"))
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)
    monkeypatch.setattr(owner_console, "write_retrospective_event", _noop)

    await owner_console.handle_tool_call(msg, "подними цены")

    assert calls["run_tool"] == 0
    assert msg.answers
    assert "Нужно уточнить" in msg.answers[-1][0]


@pytest.mark.asyncio
async def test_llm_capability_unsupported_returns_upstream_not_implemented(monkeypatch) -> None:
    from app.bot.routers import owner_console
    from app.tools.impl.sis_fx_reprice_auto import Payload as FxPayload

    msg = _DummyMessage()
    calls = {"run_tool": 0}

    async def _llm_plan_intent(**kwargs):
        return LLMIntent(intent_kind="TOOL", tool="sis_fx_reprice_auto", payload={"force": False}, confidence=0.9), "MOCK"

    async def _run_tool(*args, **kwargs):
        calls["run_tool"] += 1
        return ToolResponse.ok(correlation_id="c", data={}, provenance=ToolProvenance(sources=["demo"]))

    async def _noop(*args, **kwargs):
        return None

    async def _caps(**kwargs):
        return {"capabilities": {"fx": {"supported": False}}}

    monkeypatch.setattr(owner_console, "route_intent", lambda text: SimpleNamespace(tool=None, payload={}, presentation=None, error_message="Не понял"))
    monkeypatch.setattr(owner_console, "llm_plan_intent", _llm_plan_intent)
    monkeypatch.setattr(owner_console.registry, "get", lambda name: ToolDefinition(name=name, version="1", payload_model=FxPayload, handler=None, kind="action"))
    monkeypatch.setattr(owner_console, "run_tool", _run_tool)
    monkeypatch.setattr(owner_console, "get_settings", lambda: SimpleNamespace(upstream_mode="SIS_HTTP", llm_provider="MOCK"))
    monkeypatch.setattr(owner_console, "get_sis_capabilities", _caps)
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)
    monkeypatch.setattr(owner_console, "write_retrospective_event", _noop)

    await owner_console.handle_tool_call(msg, "обнови цены по курсу")

    assert calls["run_tool"] == 0
    assert "UPSTREAM_NOT_IMPLEMENTED" in msg.answers[-1][0]


@pytest.mark.asyncio
async def test_voice_path_uses_handle_tool_call(monkeypatch) -> None:
    from app.bot.routers import owner_console

    class _Attachment:
        duration = 1
        mime_type = "audio/ogg"
        file_id = "f1"

    class _Stream:
        async def read(self):
            return b"audio-bytes"

    class _Bot:
        async def get_file(self, file_id):
            return SimpleNamespace(file_path="voice.ogg")

        async def download_file(self, file_path):
            return _Stream()

    msg = _DummyMessage()
    msg.voice = _Attachment()
    msg.audio = None
    msg.document = None
    msg.bot = _Bot()

    called = {}

    async def _handle_tool_call(message, text, *, input_kind="text"):
        called["text"] = text
        called["input_kind"] = input_kind

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(owner_console, "get_settings", lambda: SimpleNamespace(asr_max_seconds=120, asr_max_bytes=10_000, asr_provider="MOCK", asr_confidence_threshold=0.1, asr_convert_voice_ogg_to_wav=False))
    monkeypatch.setattr(owner_console, "get_redis", _noop)
    monkeypatch.setattr(owner_console, "get_asr_provider", lambda settings: object())

    async def _transcribe(redis, provider, audio):
        return SimpleNamespace(text="пинг менеджеру", confidence=0.9)

    async def _templates(*args, **kwargs):
        return False

    monkeypatch.setattr(owner_console, "get_or_transcribe", _transcribe)
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)
    monkeypatch.setattr(owner_console, "_handle_voice_templates_shortcut", _templates)
    monkeypatch.setattr(owner_console, "handle_tool_call", _handle_tool_call)

    await owner_console.handle_voice(msg)

    assert called["text"] == "пинг менеджеру"
    assert called["input_kind"] == "voice"
