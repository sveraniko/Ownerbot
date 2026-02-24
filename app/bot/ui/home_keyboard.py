from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Отчеты", callback_data="ui:dash")],
            [InlineKeyboardButton(text="🧾 Заказы", callback_data="ui:orders")],
            [InlineKeyboardButton(text="💸 Цены (FX)", callback_data="ui:prices")],
            [InlineKeyboardButton(text="📦 Товары", callback_data="ui:products")],
            [InlineKeyboardButton(text="🔔 Уведомления", callback_data="ui:notify")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="ui:systems")],
        ]
    )
