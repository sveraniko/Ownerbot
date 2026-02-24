from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.settings import get_settings


def _with_home(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    rows.append([InlineKeyboardButton(text="🏠 Главная", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_dashboard_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "📊 Отчеты\n\n"
        "• Бизнес-сводка и KPI\n"
        "• Тренды выручки\n"
        "• Регулярные отчёты\n"
        "• Быстрый запуск ключевых отчётов"
    )
    keyboard = _with_home(
        [
            [InlineKeyboardButton(text="🔥 Что горит", callback_data="ui:focus:burn")],
            [InlineKeyboardButton(text="💰 Деньги сегодня", callback_data="ui:focus:money")],
            [InlineKeyboardButton(text="📦 Риски склада", callback_data="ui:focus:stock")],
            [InlineKeyboardButton(text="KPI вчера", callback_data="tpl:run:RPT_KPI_YESTERDAY")],
            [InlineKeyboardButton(text="KPI 7 дней", callback_data="tpl:run:RPT_KPI_7D")],
            [InlineKeyboardButton(text="Выручка тренд 30д (PNG)", callback_data="tpl:run:RPT_REVENUE_TREND_30D")],
            [InlineKeyboardButton(text="Отчёт за неделю (PDF)", callback_data="tpl:run:RPT_WEEKLY_PDF")],
            [InlineKeyboardButton(text="Дневной дашборд (PNG)", callback_data="tpl:run:BIZ_DASHBOARD_DAILY_PNG")],
            [InlineKeyboardButton(text="Все отчёты…", callback_data="tpl:cat:reports:p:0")],
        ]
    )
    return text, keyboard


def build_focus_burn_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🔥 Что горит\n\n"
        "• Зависшие и проблемные оплаты\n"
        "• Чаты без ответа\n"
        "• Последние ошибки/варнинги\n"
        "• Быстрый запуск точечных проверок"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сводка зависших", callback_data="tpl:run:RPT_STUCK_ORDERS_SUMMARY")],
            [InlineKeyboardButton(text="Проблемы оплаты", callback_data="tpl:run:ORD_PAYMENT_ISSUES")],
            [InlineKeyboardButton(text="Чаты без ответа", callback_data="tpl:run:RPT_UNANSWERED_CHATS_SUMMARY")],
            [InlineKeyboardButton(text="Последние ошибки/варнинги", callback_data="tpl:run:SYS_LAST_ERRORS")],
            [
                InlineKeyboardButton(text="⬅️ Отчеты", callback_data="ui:dash"),
                InlineKeyboardButton(text="🏠 Главная", callback_data="ui:home"),
            ],
        ]
    )
    return text, keyboard


def build_focus_money_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "💰 Деньги сегодня\n\n"
        "• KPI и сравнение с вчера\n"
        "• Тренд выручки\n"
        "• FX статус и пересчёт"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="KPI сегодня", callback_data="tpl:run:RPT_KPI_TODAY")],
            [InlineKeyboardButton(text="KPI вчера", callback_data="tpl:run:RPT_KPI_YESTERDAY")],
            [InlineKeyboardButton(text="Тренд 30д (PNG)", callback_data="tpl:run:RPT_REVENUE_TREND_30D_PNG")],
            [InlineKeyboardButton(text="Сравнение неделя/неделя", callback_data="tpl:run:RPT_COMPARE_WOW")],
            [InlineKeyboardButton(text="FX статус", callback_data="tpl:run:PRC_FX_STATUS")],
            [InlineKeyboardButton(text="FX предпросмотр", callback_data="tpl:run:PRC_FX_AUTO")],
            [InlineKeyboardButton(text="Применить FX", callback_data="tpl:run:PRC_FX_REPRICE")],
            [
                InlineKeyboardButton(text="⬅️ Отчеты", callback_data="ui:dash"),
                InlineKeyboardButton(text="🏠 Главная", callback_data="ui:home"),
            ],
        ]
    )
    return text, keyboard


def build_focus_stock_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "📦 Риски склада\n\n"
        "• Остатки и статус каталога\n"
        "• Карточки без фото/цены\n"
        "• Быстрый фокус на проблемные позиции"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Остатки", callback_data="tpl:run:PRD_INVENTORY_STATUS")],
            [InlineKeyboardButton(text="Мало на складе", callback_data="tpl:run:PRD_LOW_STOCK")],
            [InlineKeyboardButton(text="Без фото", callback_data="tpl:run:PRD_NO_PHOTO")],
            [InlineKeyboardButton(text="Без цены", callback_data="tpl:run:PRD_NO_PRICE")],
            [InlineKeyboardButton(text="Топ товаров 7д", callback_data="tpl:run:RPT_TOP_PRODUCTS_7D")],
            [
                InlineKeyboardButton(text="⬅️ Отчеты", callback_data="ui:dash"),
                InlineKeyboardButton(text="🏠 Главная", callback_data="ui:home"),
            ],
        ]
    )
    return text, keyboard


def build_orders_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = "🧾 Заказы\n\nОперации с заказами: контроль зависших, чатов и быстрый поиск."
    keyboard = _with_home(
        [
            [InlineKeyboardButton(text="Зависшие (сводка)", callback_data="tpl:run:ORD_STUCK_LIST")],
            [InlineKeyboardButton(text="Непрочитанные чаты", callback_data="tpl:run:TEAM_UNANSWERED_2H")],
            [InlineKeyboardButton(text="Найти заказ по ID", callback_data="tpl:run:ORD_FIND_BY_ID")],
            [InlineKeyboardButton(text="Последние заказы", callback_data="tpl:run:ORD_FIND_RECENT")],
            [InlineKeyboardButton(text="Все шаблоны заказов…", callback_data="tpl:cat:orders:p:0")],
        ]
    )
    return text, keyboard


def build_prices_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = "💸 Цены (FX)\n\nКонтроль FX-режима, проверка настроек и репрайс."
    keyboard = _with_home(
        [
            [InlineKeyboardButton(text="FX статус", callback_data="tpl:run:PRC_FX_STATUS")],
            [InlineKeyboardButton(text="FX настройки", callback_data="fx:panel")],
            [InlineKeyboardButton(text="FX репрайс", callback_data="tpl:run:PRC_FX_REPRICE")],
            [InlineKeyboardButton(text="Авто FX", callback_data="tpl:run:PRC_FX_AUTO")],
            [InlineKeyboardButton(text="Все цены…", callback_data="tpl:cat:prices:p:0")],
        ]
    )
    return text, keyboard


def build_products_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = "📦 Товары\n\nКачество каталога и остатки: проверки карточек и инвентаря."
    keyboard = _with_home(
        [
            [InlineKeyboardButton(text="Без цены", callback_data="tpl:run:PRD_NO_PRICE")],
            [InlineKeyboardButton(text="Без фото", callback_data="tpl:run:PRD_NO_PHOTO")],
            [InlineKeyboardButton(text="Мало на складе", callback_data="tpl:run:PRD_LOW_STOCK")],
            [InlineKeyboardButton(text="Остатки", callback_data="tpl:run:PRD_INVENTORY_STATUS")],
            [InlineKeyboardButton(text="Все товары…", callback_data="tpl:cat:products:p:0")],
        ]
    )
    return text, keyboard


def build_notifications_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = "🔔 Уведомления\n\nУправление дайджестами и подписками уведомлений."
    keyboard = _with_home(
        [
            [InlineKeyboardButton(text="Статус", callback_data="tpl:run:NTF_STATUS")],
            [InlineKeyboardButton(text="Отправить дайджест", callback_data="tpl:run:NTF_SEND_DIGEST_NOW")],
            [InlineKeyboardButton(text="Отправить недельный", callback_data="tpl:run:NTF_SEND_WEEKLY_NOW")],
            [InlineKeyboardButton(text="➕ Подписка дайджест", callback_data="tpl:run:NTF_DAILY_DIGEST_SUBSCRIBE")],
            [InlineKeyboardButton(text="➖ Отписка дайджест", callback_data="tpl:run:NTF_DAILY_DIGEST_UNSUBSCRIBE")],
            [InlineKeyboardButton(text="➕ Подписка FX", callback_data="tpl:run:NTF_FX_DELTA_SUBSCRIBE")],
            [InlineKeyboardButton(text="➖ Отписка FX", callback_data="tpl:run:NTF_FX_DELTA_UNSUBSCRIBE")],
            [InlineKeyboardButton(text="Все уведомления…", callback_data="tpl:cat:notifications:p:0")],
        ]
    )
    return text, keyboard


def build_systems_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = "⚙️ Настройки\n\nИнфраструктура, диагностика и служебные панели управления."
    keyboard = _with_home(
        [
            [InlineKeyboardButton(text="Здоровье системы", callback_data="tpl:run:SYS_HEALTH")],
            [InlineKeyboardButton(text="Последние действия", callback_data="tpl:run:SYS_AUDIT_RECENT")],
            [InlineKeyboardButton(text="Ошибки", callback_data="tpl:run:SYS_LAST_ERRORS")],
            [InlineKeyboardButton(text="Возможности SIS", callback_data="tpl:run:SYS_SIS_ACTIONS_CAPABILITIES")],
            [InlineKeyboardButton(text="Статус онбординга", callback_data="tpl:run:SYS_ONBOARD_STATUS")],
            [InlineKeyboardButton(text="🔌 Источник данных", callback_data="ui:upstream")],
            [InlineKeyboardButton(text="🧰 Инструменты", callback_data="ui:tools")],
            [InlineKeyboardButton(text="📚 Шаблоны", callback_data="ui:templates")],
        ]
    )
    return text, keyboard


def build_tools_panel() -> tuple[str, InlineKeyboardMarkup]:
    settings = get_settings()
    tools = settings.llm_allowed_action_tools
    top = tools[:8]
    text = (
        "🧰 Инструменты\n\n"
        f"Доступно: {len(tools)}\n"
        f"Первые {len(top)}:\n"
        + ("\n".join(f"• {name}" for name in top) if top else "• нет")
    )
    keyboard = _with_home(
        [
            [InlineKeyboardButton(text="Список полностью (JSON)", callback_data="tpl:run:ADV_EXPORT_JSON")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="ui:systems")],
        ]
    )
    return text, keyboard
