from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolArtifact, ToolProvenance, ToolResponse


class _DummyMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=42)
        self.text = None
        self.bot = object()
        self.answers = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_template_run_sends_dashboard_pdf_artifact(monkeypatch) -> None:
    from app.bot.routers import templates

    async def _resolve(**kwargs):
        return "DEMO", None

    async def _choose(**kwargs):
        return "DEMO", None

    async def _redis():
        return SimpleNamespace()

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(
            correlation_id="cid",
            data={"message": "dashboard ready"},
            artifacts=[ToolArtifact(type="pdf", filename="dash.pdf", content=b"%PDF-mock", caption="weekly")],
            provenance=ToolProvenance(sources=["biz_dashboard"], window={}),
        )

    sent = {"doc": 0, "msg": 0}

    class _Sender:
        def __init__(self, bot):
            self.bot = bot

        async def _safe_send_document(self, *args, **kwargs):
            sent["doc"] += 1
            return True

        async def _safe_send_message(self, *args, **kwargs):
            sent["msg"] += 1
            return True

        async def _safe_send_photo(self, *args, **kwargs):
            raise AssertionError("photo not expected")

    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)
    monkeypatch.setattr("app.bot.routers.templates.NotifyWorker", _Sender)

    msg = _DummyMessage()
    await templates._run_template_action(
        message=msg,
        owner_user_id=42,
        spec=SimpleNamespace(tool_name="biz_dashboard_weekly", presentation=None),
        payload={"format": "pdf"},
    )

    assert sent["doc"] == 1
    assert sent["msg"] == 1


@pytest.mark.asyncio
async def test_template_run_sends_ops_pdf_artifact(monkeypatch) -> None:
    from app.bot.routers import templates

    async def _resolve(**kwargs):
        return "DEMO", None

    async def _choose(**kwargs):
        return "DEMO", None

    async def _redis():
        return SimpleNamespace()

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(
            correlation_id="cid",
            data={"message": "ops dashboard ready"},
            artifacts=[ToolArtifact(type="pdf", filename="ops.pdf", content=b"%PDF-mock", caption="ops")],
            provenance=ToolProvenance(sources=["biz_dashboard_ops"], window={}),
        )

    sent = {"doc": 0, "msg": 0}

    class _Sender:
        def __init__(self, bot):
            self.bot = bot

        async def _safe_send_document(self, *args, **kwargs):
            sent["doc"] += 1
            return True

        async def _safe_send_message(self, *args, **kwargs):
            sent["msg"] += 1
            return True

        async def _safe_send_photo(self, *args, **kwargs):
            raise AssertionError("photo not expected")

    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)
    monkeypatch.setattr("app.bot.routers.templates.NotifyWorker", _Sender)

    msg = _DummyMessage()
    await templates._run_template_action(
        message=msg,
        owner_user_id=42,
        spec=SimpleNamespace(tool_name="biz_dashboard_ops", presentation=None),
        payload={"format": "pdf", "tz": "Europe/Berlin"},
    )

    assert sent["doc"] == 1
    assert sent["msg"] == 1
