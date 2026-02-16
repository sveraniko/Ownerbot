from types import SimpleNamespace

import pytest

from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning


async def _redis():
    return SimpleNamespace()


class _DummyPanel:
    def __init__(self) -> None:
        self.calls = []

    async def show_panel(self, message, text: str, *, inline_kb=None, mode="replace"):
        self.calls.append((text, inline_kb, mode))


class _DummyMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=42)
        self.chat = SimpleNamespace(id=100)
        self.text = None
        self.bot = SimpleNamespace()


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

    panel = _DummyPanel()
    monkeypatch.setattr("app.bot.routers.templates.get_panel_manager", lambda: panel)
    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)
    monkeypatch.setattr("app.bot.routers.templates.create_confirm_token", _create_token)
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)

    msg = _DummyMessage()
    await templates._run_template_action(msg, 42, "sis_fx_reprice", {"dry_run": True, "rate_set_id": "h", "input_currency": "USD", "shop_currency": "EUR"})

    _, markup, _ = panel.calls[0]
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

    panel = _DummyPanel()
    monkeypatch.setattr("app.bot.routers.templates.get_panel_manager", lambda: panel)
    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)
    monkeypatch.setattr("app.bot.routers.templates.create_confirm_token", _create_token)
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)

    msg = _DummyMessage()
    await templates._run_template_action(msg, 42, "sis_prices_bump", {"dry_run": True, "bump_percent": "10"})

    _, markup, _ = panel.calls[0]
    flat = [b.text for row in markup.inline_keyboard for b in row]
    assert "✅ Подтвердить" in flat


@pytest.mark.asyncio
async def test_template_flow_dry_run_noop_skips_confirm(monkeypatch) -> None:
    from app.bot.routers import templates

    async def _resolve(**kwargs):
        return "DEMO", None

    async def _choose(**kwargs):
        return "DEMO", None

    async def _run_tool(*args, **kwargs):
        return ToolResponse.ok(
            correlation_id="corr",
            data={"would_apply": False, "status": "noop"},
            provenance=ToolProvenance(sources=["sis"]),
        )

    async def _create_token(payload):
        raise AssertionError("confirm token must not be created for no-op preview")

    panel = _DummyPanel()
    monkeypatch.setattr("app.bot.routers.templates.get_panel_manager", lambda: panel)
    monkeypatch.setattr("app.bot.routers.templates.resolve_effective_mode", _resolve)
    monkeypatch.setattr("app.bot.routers.templates.choose_data_mode", _choose)
    monkeypatch.setattr("app.bot.routers.templates.run_tool", _run_tool)
    monkeypatch.setattr("app.bot.routers.templates.create_confirm_token", _create_token)
    monkeypatch.setattr("app.bot.routers.templates.get_redis", _redis)

    msg = _DummyMessage()
    await templates._run_template_action(msg, 42, "sis_fx_reprice_auto", {"dry_run": True})

    _, markup, _ = panel.calls[0]
    assert markup is None


@pytest.mark.asyncio
async def test_consume_step_value_runs_action_when_inputs_finished(monkeypatch) -> None:
    from app.bot.routers import templates
    from app.templates.catalog.models import TemplateSpec

    called = []

    async def _set_state(*args, **kwargs):
        raise AssertionError("must not set next state when final step")

    async def _clear_state(user_id: int):
        called.append(("clear", user_id))

    async def _run_action(message, owner_user_id, tool_name, payload):
        called.append(("run", owner_user_id, tool_name, payload))

    async def _get_state(user_id: int):
        return {"payload_partial": {}}

    monkeypatch.setattr("app.bot.routers.templates._set_state", _set_state)
    monkeypatch.setattr("app.bot.routers.templates._clear_state", _clear_state)
    monkeypatch.setattr("app.bot.routers.templates._run_template_action", _run_action)
    monkeypatch.setattr("app.bot.routers.templates._get_state", _get_state)

    spec = TemplateSpec(
        template_id="X",
        category="prices",
        title="t",
        button_text="b",
        kind="ACTION",
        tool_name="sis_prices_bump",
        default_payload={},
        inputs=[{"key": "bump_percent", "prompt": "p", "parser": "int"}],
    )

    msg = _DummyMessage()
    await templates._consume_step_value(msg, 42, spec, 0, "10")

    assert called[0] == ("clear", 42)
    assert called[1][0:2] == ("run", 42)
    assert called[1][2].tool_name == "sis_prices_bump"
    assert called[1][3] == {"bump_percent": 10, "dry_run": True}


@pytest.mark.asyncio
async def test_consume_step_value_parser_error_uses_panel(monkeypatch) -> None:
    from app.bot.routers import templates
    from app.templates.catalog.models import TemplateSpec

    panel = _DummyPanel()

    async def _get_state(user_id: int):
        return {"payload_partial": {}}

    monkeypatch.setattr("app.bot.routers.templates._get_state", _get_state)
    monkeypatch.setattr("app.bot.routers.templates.get_panel_manager", lambda: panel)

    spec = TemplateSpec(
        template_id="X",
        category="discounts",
        title="t",
        button_text="b",
        kind="ACTION",
        tool_name="sis_discounts_set",
        default_payload={},
        inputs=[{"key": "discount_percent", "prompt": "p", "parser": "percent_1_95"}],
    )

    msg = _DummyMessage()
    await templates._consume_step_value(msg, 42, spec, 0, "0")

    assert "Процент скидки должен быть от 1 до 95." in panel.calls[0][0]
