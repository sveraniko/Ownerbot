from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in rows]
    )


def build_templates_main_keyboard() -> InlineKeyboardMarkup:
    return _kb([[('💸 Цены', 'tpl:prices')], [('📦 Товары', 'tpl:products')], [('🏷️ Скидки', 'tpl:discounts')]])


def build_templates_prices_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [("Поднять цены на %", "tpl:prices:bump")],
            [("FX пересчёт цен", "tpl:prices:fx")],
            [("FX статус", "tpl:prices:fx:status")],
            [("FX обновить (по настройкам)", "tpl:prices:fx:auto")],
            [("FX расписание/пороги", "tpl:prices:fx:settings")],
            [("Откат последнего FX", "tpl:prices:rollback")],
        ]
    )


def build_templates_products_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [("Опубликовать товары (по ID)", "tpl:products:publish:ids")],
            [("Снять с публикации товары (по ID)", "tpl:products:archive:ids")],
            [("Опубликовать ВСЕ товары", "tpl:products:publish:all")],
            [("Снять с публикации ВСЕ товары", "tpl:products:archive:all")],
            [("Луки", "tpl:looks")],
        ]
    )


def build_templates_looks_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [("Опубликовать луки (по ID)", "tpl:looks:publish:ids")],
            [("Снять с публикации луки (по ID)", "tpl:looks:archive:ids")],
            [("Опубликовать ВСЕ луки", "tpl:looks:publish:all")],
            [("Снять ВСЕ луки", "tpl:looks:archive:all")],
        ]
    )


def build_templates_discounts_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [("Удалить скидки (по ID товаров)", "tpl:discounts:clear:ids")],
            [("Удалить ВСЕ скидки", "tpl:discounts:clear:all")],
            [("Поставить скидку % (по ID товаров)", "tpl:discounts:set:ids")],
            [("Поставить скидку % на остатки <= N", "tpl:discounts:set:stock")],
        ]
    )
