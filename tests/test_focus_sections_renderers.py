from __future__ import annotations

from app.bot.ui.sections import build_focus_burn_panel, build_focus_money_panel, build_focus_stock_panel
from app.templates.catalog import get_template_catalog


def _all_callback_data(keyboard):
    return [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]


def _assert_template_callbacks_exist(callback_data: list[str]) -> None:
    catalog = get_template_catalog()
    existing_ids = {
        template.template_id
        for category in catalog.list_categories()
        for template in catalog.list_templates(category)
    }
    for item in callback_data:
        if item.startswith("tpl:run:"):
            assert item.split(":", 2)[-1] in existing_ids


def test_focus_burn_section_renderer_contract() -> None:
    _text, keyboard = build_focus_burn_panel()
    callback_data = _all_callback_data(keyboard)
    assert "ui:home" in callback_data
    assert "ui:dash" in callback_data
    _assert_template_callbacks_exist(callback_data)


def test_focus_money_section_renderer_contract() -> None:
    _text, keyboard = build_focus_money_panel()
    callback_data = _all_callback_data(keyboard)
    assert "ui:home" in callback_data
    assert "ui:dash" in callback_data
    _assert_template_callbacks_exist(callback_data)


def test_focus_stock_section_renderer_contract() -> None:
    _text, keyboard = build_focus_stock_panel()
    callback_data = _all_callback_data(keyboard)
    assert "ui:home" in callback_data
    assert "ui:dash" in callback_data
    _assert_template_callbacks_exist(callback_data)
