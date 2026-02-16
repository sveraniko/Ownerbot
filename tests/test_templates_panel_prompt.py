from __future__ import annotations

from types import SimpleNamespace

import pytest


class _PanelStub:
    def __init__(self) -> None:
        self.calls = []

    async def show_panel(self, message, text: str, *, inline_kb=None, mode="replace"):
        self.calls.append((text, inline_kb, mode))


@pytest.mark.asyncio
async def test_prompt_current_step_uses_panel_edit(monkeypatch) -> None:
    from app.bot.routers import templates

    panel = _PanelStub()
    monkeypatch.setattr("app.bot.routers.templates.get_panel_manager", lambda: panel)

    message = SimpleNamespace(chat=SimpleNamespace(id=1), bot=SimpleNamespace())
    await templates._prompt_current_step(message, "PRC_BUMP", 0)

    assert panel.calls
    assert panel.calls[0][2] == "edit"
