from types import SimpleNamespace

import pytest


class _DummyMessage:
    def __init__(self) -> None:
        self.answers = []
        self.from_user = SimpleNamespace(id=1)

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_voice_templates_prices_shortcut(monkeypatch) -> None:
    from app.bot.routers import owner_console

    events = []

    async def _audit(name: str, payload: dict):
        events.append((name, payload))

    monkeypatch.setattr(owner_console, "write_audit_event", _audit)

    msg = _DummyMessage()
    handled = await owner_console._handle_voice_templates_shortcut(msg, "шаблоны цены")

    assert handled is True
    assert msg.answers
    text, markup = msg.answers[-1]
    assert text == "Шаблоны → Цены"
    flat = [b.text for row in markup.inline_keyboard for b in row]
    assert "Поднять цены на %" in flat
    assert any(name == "voice.route" and payload.get("selected_path") == "templates" for name, payload in events)
