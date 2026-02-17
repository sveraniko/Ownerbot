from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.templates.catalog import get_template_catalog

_PAGE_SIZE = 8
_CATEGORY_META = {
    "reports": ("📊", "Отчёты"),
    "orders": ("🧾", "Заказы"),
    "team": ("👥", "Команда"),
    "systems": ("⚙️", "Системы"),
    "advanced": ("🔧", "Advanced"),
    "forecast": ("🔮", "Прогнозы"),
    "prices": ("💸", "Цены"),
    "products": ("📦", "Товары"),
    "looks": ("👗", "Луки"),
    "discounts": ("🏷️", "Скидки"),
    "notifications": ("🔔", "Уведомления"),
}


def _label_for_category(category: str) -> str:
    icon, title = _CATEGORY_META.get(category, ("📁", category.title()))
    return f"{icon} {title}"


def build_templates_main_keyboard() -> InlineKeyboardMarkup:
    catalog = get_template_catalog()
    rows = [
        [InlineKeyboardButton(text=_label_for_category(category), callback_data=f"tpl:cat:{category}:p:0")]
        for category in catalog.list_categories()
    ]
    rows.append([InlineKeyboardButton(text="🏠 Домой", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_templates_category_keyboard(category: str, page: int = 0, templates=None) -> InlineKeyboardMarkup:
    catalog = get_template_catalog()
    templates = templates if templates is not None else catalog.list_templates(category)
    start = max(page, 0) * _PAGE_SIZE
    end = start + _PAGE_SIZE
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=spec.button_text, callback_data=f"tpl:run:{spec.template_id}")]
        for spec in templates[start:end]
    ]

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"tpl:cat:{category}:p:{page - 1}"))
    if end < len(templates):
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"tpl:cat:{category}:p:{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="Назад", callback_data="tpl:home")])
    rows.append([InlineKeyboardButton(text="🏠 Домой", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_input_presets_keyboard(template_id: str, step_index: int, presets: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text=text, callback_data=f"tpl:ps:{template_id}:{step_index}:{idx}")
        for idx, (text, _value) in enumerate(presets)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def build_templates_prices_keyboard() -> InlineKeyboardMarkup:
    return build_templates_category_keyboard("prices")


def build_templates_products_keyboard() -> InlineKeyboardMarkup:
    return build_templates_category_keyboard("products")


def build_templates_looks_keyboard() -> InlineKeyboardMarkup:
    return build_templates_category_keyboard("looks")


def build_templates_discounts_keyboard() -> InlineKeyboardMarkup:
    return build_templates_category_keyboard("discounts")


def category_title(category: str) -> str:
    return _label_for_category(category).split(" ", 1)[1]
