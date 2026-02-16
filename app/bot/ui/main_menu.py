from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def build_main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Шаблоны"), KeyboardButton(text="⚙️ Системы")],
            [KeyboardButton(text="🔌 Upstream"), KeyboardButton(text="🧰 Tools")],
            [KeyboardButton(text="🆘 Help")],
        ],
        resize_keyboard=True,
    )
