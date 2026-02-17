from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.bot.ui.home_keyboard import build_home_keyboard


def test_home_keyboard_callback_contract() -> None:
    keyboard = build_home_keyboard()
    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert not isinstance(keyboard, ReplyKeyboardMarkup)

    callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callback_data == [
        "ui:dash",
        "ui:orders",
        "ui:prices",
        "ui:products",
        "ui:notify",
        "ui:systems",
    ]
