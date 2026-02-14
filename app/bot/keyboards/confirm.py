from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_keyboard(confirm_data: str, cancel_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=confirm_data),
                InlineKeyboardButton(text="❌ Отменить", callback_data=cancel_data),
            ]
        ]
    )


def confirm_keyboard_with_force(confirm_data: str, force_confirm_data: str, cancel_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Применить", callback_data=confirm_data)],
            [InlineKeyboardButton(text="⚠️ Применить несмотря на аномалию", callback_data=force_confirm_data)],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=cancel_data)],
        ]
    )
