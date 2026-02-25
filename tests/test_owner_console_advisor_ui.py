from __future__ import annotations

from types import SimpleNamespace

import pytest


class _DummyCallbackMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=100)
        self.edits = []

    async def edit_text(self, text: str, reply_markup=None):
        self.edits.append((text, reply_markup))

    async def answer(self, text: str, reply_markup=None):
        self.edits.append((text, reply_markup))


class _DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=77)
        self.message = _DummyCallbackMessage()

    async def answer(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_advisor_preset_renders_anchor_and_buttons(monkeypatch) -> None:
    from app.bot.routers import owner_console

    class _Redis:
        async def set(self, *args, **kwargs):
            return True

    async def _get_redis():
        return _Redis()

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(owner_console, "get_redis", _get_redis)
    monkeypatch.setattr(owner_console, "write_audit_event", _noop)

    cb = _DummyCallback("advisor:preset:SEASON_TRENDS")
    await owner_console.advisor_preset(cb)

    assert cb.message.edits
    text, keyboard = cb.message.edits[-1]
    assert "Гипотезы" in text
    all_buttons = [b.text for row in keyboard.inline_keyboard for b in row]
    assert "✅ Проверить данными" in all_buttons
    assert "🧩 Предложить действия (preview)" in all_buttons
