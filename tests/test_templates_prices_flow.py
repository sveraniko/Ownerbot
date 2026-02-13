from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning


class _DummyMessage:
    def __init__(self) -> None:
        self.calls = []

    async def answer(self, text: str, reply_markup=None):
        self.calls.append((text, reply_markup))


@pytest.mark.asyncio
async def test_template_flow_dry_run_creates_force_confirm_buttons(monkeypatch) -> None:
    from app.bot.routers import templates

    async def _resolve(**kwargs):
        return "DEMO", None

    async def _choose(**kwargs):
        return "DEMO", None

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(
            correlation_id="corr",
            data={"affected_count": 5, "anomaly": {"over_threshold_count": 1}},
            provenance=ToolProvenance(sources=["sis"]),
            warnings=[ToolWarning(code="SIS_WARNING", message="force required for apply")],
        )

    tokens = ["tok-normal", "tok-force"]

    async def _create_token(payload):
        return tokens.pop(0)

    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)
    monkeypatch.setattr("app.bot.routers.templates.create_confirm_token", _create_token)

    msg = _DummyMessage()
    await templates._run_template_action(msg, 42, "sis_fx_reprice", {"dry_run": True, "rate_set_id": "h", "input_currency": "USD", "shop_currency": "EUR"})

    assert len(msg.calls) == 1
    text, markup = msg.calls[0]
    assert "affected_count" in text
    assert markup is not None
    flat = [b.text for row in markup.inline_keyboard for b in row]
    assert "✅ Применить" in flat
    assert "⚠️ Применить несмотря на аномалию" in flat


@pytest.mark.asyncio
async def test_template_flow_dry_run_default_confirm_button(monkeypatch) -> None:
    from app.bot.routers import templates

    async def _resolve(**kwargs):
        return "DEMO", None

    async def _choose(**kwargs):
        return "DEMO", None

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(
            correlation_id="corr",
            data={"affected_count": 5, "anomaly": {"over_threshold_count": 0}},
            provenance=ToolProvenance(sources=["sis"]),
        )

    async def _create_token(payload):
        return "tok-normal"

    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)
    monkeypatch.setattr("app.bot.routers.templates.create_confirm_token", _create_token)

    msg = _DummyMessage()
    await templates._run_template_action(msg, 42, "sis_prices_bump", {"dry_run": True, "bump_percent": "10"})

    _, markup = msg.calls[0]
    flat = [b.text for row in markup.inline_keyboard for b in row]
    assert "✅ Подтвердить" in flat
