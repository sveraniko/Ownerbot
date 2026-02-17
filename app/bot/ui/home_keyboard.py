from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Dashboard", callback_data="ui:dash")],
            [InlineKeyboardButton(text="🧾 Orders", callback_data="ui:orders")],
            [InlineKeyboardButton(text="💸 Prices (FX)", callback_data="ui:prices")],
            [InlineKeyboardButton(text="📦 Products", callback_data="ui:products")],
            [InlineKeyboardButton(text="🔔 Notifications", callback_data="ui:notify")],
            [InlineKeyboardButton(text="⚙️ Systems", callback_data="ui:systems")],
        ]
    )
