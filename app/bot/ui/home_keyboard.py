from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Шаблоны", callback_data="ui:templates")],
            [InlineKeyboardButton(text="⚙️ Системы", callback_data="ui:systems")],
            [InlineKeyboardButton(text="🔌 Upstream", callback_data="ui:upstream")],
            [InlineKeyboardButton(text="🧰 Tools", callback_data="ui:tools")],
            [InlineKeyboardButton(text="🆘 Help", callback_data="ui:help")],
        ]
    )
