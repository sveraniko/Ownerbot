from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning


async def _redis():
    return SimpleNamespace()


class _DummyMessage:
    def __init__(self) -> None:
        self.calls = []
        self.from_user = SimpleNamespace(id=42)
        self.text = None

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
            data={"affected_count": 5, "anomaly": {"over_threshold_count": 0}},
            provenance=ToolProvenance(sources=["sis"]),
            warnings=[ToolWarning(code="FORCE_REQUIRED", message="Need force")],
        )

    tokens = ["tok-normal", "tok-force"]

    async def _create_token(payload):
        return tokens.pop(0)

    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)
    monkeypatch.setattr("app.bot.routers.templates.create_confirm_token", _create_token)
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)

    msg = _DummyMessage()
    await templates._run_template_action(msg, 42, "sis_fx_reprice", {"dry_run": True, "rate_set_id": "h", "input_currency": "USD", "shop_currency": "EUR"})

    _, markup = msg.calls[0]
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
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)

    msg = _DummyMessage()
    await templates._run_template_action(msg, 42, "sis_prices_bump", {"dry_run": True, "bump_percent": "10"})

    _, markup = msg.calls[0]
    flat = [b.text for row in markup.inline_keyboard for b in row]
    assert "✅ Подтвердить" in flat


def test_template_parse_helpers() -> None:
    from app.bot.routers.templates import _parse_ids, _parse_percent, _parse_stock_threshold

    assert _parse_ids("a, b\nc") == ["a", "b", "c"]
    assert _parse_percent("25") == 25
    assert _parse_stock_threshold("9") == 9

    with pytest.raises(ValueError):
        _parse_ids("  ")
    with pytest.raises(ValueError):
        _parse_percent("96")
    with pytest.raises(ValueError):
        _parse_stock_threshold("0")
