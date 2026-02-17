from __future__ import annotations

from app.bot.ui.sections import (
    build_dashboard_panel,
    build_notifications_panel,
    build_orders_panel,
    build_prices_panel,
    build_products_panel,
    build_systems_panel,
)
from app.templates.catalog import get_template_catalog


def _all_callback_data(keyboard):
    return [button.callback_data for row in keyboard.inline_keyboard for button in row if button.callback_data]


def _assert_has_home_button(callback_data: list[str]) -> None:
    assert "ui:home" in callback_data


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


def test_dashboard_section_renderer_contract() -> None:
    _text, keyboard = build_dashboard_panel()
    callback_data = _all_callback_data(keyboard)
    _assert_has_home_button(callback_data)
    _assert_template_callbacks_exist(callback_data)
    assert "tpl:cat:reports:p:0" in callback_data


def test_orders_section_renderer_contract() -> None:
    _text, keyboard = build_orders_panel()
    callback_data = _all_callback_data(keyboard)
    _assert_has_home_button(callback_data)
    _assert_template_callbacks_exist(callback_data)
    assert "tpl:cat:orders:p:0" in callback_data


def test_prices_section_renderer_contract() -> None:
    _text, keyboard = build_prices_panel()
    callback_data = _all_callback_data(keyboard)
    _assert_has_home_button(callback_data)
    _assert_template_callbacks_exist(callback_data)
    assert "tpl:cat:prices:p:0" in callback_data


def test_products_section_renderer_contract() -> None:
    _text, keyboard = build_products_panel()
    callback_data = _all_callback_data(keyboard)
    _assert_has_home_button(callback_data)
    _assert_template_callbacks_exist(callback_data)
    assert "tpl:cat:products:p:0" in callback_data


def test_notifications_section_renderer_contract() -> None:
    _text, keyboard = build_notifications_panel()
    callback_data = _all_callback_data(keyboard)
    _assert_has_home_button(callback_data)
    _assert_template_callbacks_exist(callback_data)
    assert "tpl:cat:notifications:p:0" in callback_data


def test_systems_section_renderer_contract() -> None:
    _text, keyboard = build_systems_panel()
    callback_data = _all_callback_data(keyboard)
    _assert_has_home_button(callback_data)
    _assert_template_callbacks_exist(callback_data)
    assert "ui:upstream" in callback_data
    assert "ui:tools" in callback_data
    assert "ui:templates" in callback_data
