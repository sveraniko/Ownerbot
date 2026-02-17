from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.bot.ui.home_keyboard import build_home_keyboard


def test_home_keyboard_callback_contract() -> None:
    keyboard = build_home_keyboard()
    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert not isinstance(keyboard, ReplyKeyboardMarkup)

    for row in keyboard.inline_keyboard:
        for button in row:
            assert button.callback_data is not None
            assert button.callback_data.startswith("ui:")
            assert len(button.callback_data.encode("utf-8")) <= 64
