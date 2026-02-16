from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolArtifact, ToolProvenance, ToolResponse


class _DummyPanel:
    def __init__(self) -> None:
        self.tracked = []
        self.shown = []

    async def track_transient(self, chat_id: int, message_id: int) -> None:
        self.tracked.append((chat_id, message_id))

    async def show_panel(self, message, text: str, *, inline_kb=None, mode="replace") -> None:
        self.shown.append((text, mode))


class _BotStub:
    def __init__(self) -> None:
        self.sent_docs = 0
        self.sent_photos = 0
        self.next_id = 100

    async def send_document(self, **kwargs):
        self.sent_docs += 1
        self.next_id += 1
        return SimpleNamespace(message_id=self.next_id)

    async def send_photo(self, **kwargs):
        self.sent_photos += 1
        self.next_id += 1
        return SimpleNamespace(message_id=self.next_id)


class _DummyMessage:
    def __init__(self, bot) -> None:
        self.from_user = SimpleNamespace(id=42)
        self.chat = SimpleNamespace(id=4242)
        self.text = None
        self.bot = bot


@pytest.mark.asyncio
async def test_template_run_tracks_pdf_artifact(monkeypatch) -> None:
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

    panel = _DummyPanel()
    bot = _BotStub()

    monkeypatch.setattr("app.bot.routers.templates.get_panel_manager", lambda: panel)
    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)

    msg = _DummyMessage(bot)
    await templates._run_template_action(
        message=msg,
        owner_user_id=42,
        spec=SimpleNamespace(tool_name="biz_dashboard_weekly", presentation=None),
        payload={"format": "pdf"},
    )

    assert bot.sent_docs == 1
    assert panel.tracked
    assert panel.shown


@pytest.mark.asyncio
async def test_template_run_tracks_png_artifact(monkeypatch) -> None:
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
            data={"message": "chart ready"},
            artifacts=[ToolArtifact(type="png", filename="dash.png", content=b"PNG", caption="chart")],
            provenance=ToolProvenance(sources=["biz_dashboard_ops"], window={}),
        )

    panel = _DummyPanel()
    bot = _BotStub()

    monkeypatch.setattr("app.bot.routers.templates.get_panel_manager", lambda: panel)
    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)

    msg = _DummyMessage(bot)
    await templates._run_template_action(
        message=msg,
        owner_user_id=42,
        spec=SimpleNamespace(tool_name="biz_dashboard_ops", presentation=None),
        payload={"format": "png"},
    )

    assert bot.sent_photos == 1
    assert panel.tracked
    assert panel.shown
