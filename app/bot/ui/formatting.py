from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.tools.contracts import ToolDefinition, ToolResponse
from app.bot.ui.presenters import detect_and_format
from app.bot.ui.pagination import (
    build_pagination_keyboard,
    format_page,
    get_page_items,
    get_title_for_type,
    store_paginated_data,
)


SIS_SOURCE_TAG = "SIS"
DEMO_SOURCE_TAG = "DEMO"

# Маппинг английских полей на русские названия
_FIELD_TRANSLATIONS = {
    "day": "дата",
    "revenue_gross": "выручка брутто",
    "revenue_net": "выручка нетто",
    "orders_paid": "оплачено заказов",
    "orders_created": "создано заказов",
    "aov": "средний чек",
    "status": "статус",
    "base_currency": "базовая валюта",
    "shop_currency": "валюта магазина",
    "latest_rate": "текущий курс",
    "next_reprice_in_hours": "до пересчёта (час)",
    "would_apply": "нужен пересчёт",
    "orders_total": "всего заказов",
    "orders_stuck": "зависших",
    "chats_unanswered": "чатов без ответа",
    "total_products": "всего товаров",
    "low_stock_count": "мало на складе",
    "no_price_count": "без цены",
    "no_photo_count": "без фото",
    "active_count": "активных",
    "archived_count": "в архиве",
    "enabled": "включено",
    "disabled": "выключено",
    "fx_enabled": "FX включён",
    "last_reprice": "посл. пересчёт",
    "count": "кол-во",
    "total": "всего",
    "success": "успешно",
    "error": "ошибка",
    "pending": "в ожидании",
}

# Маппинг значений
_VALUE_TRANSLATIONS = {
    "True": "да",
    "False": "нет",
    "ok": "ок",
    "error": "ошибка",
    "none": "нет",
}


def _translate_field(key: str) -> str:
    return _FIELD_TRANSLATIONS.get(key, key)


def _translate_value(value) -> str:
    str_val = str(value)
    return _VALUE_TRANSLATIONS.get(str_val, str_val)


def detect_source_tag(resp: ToolResponse) -> str | None:
    sources = resp.provenance.sources if resp.provenance else []
    joined = " ".join(sources).lower()
    if "ownerbot/v1" in joined or "sis" in joined:
        return SIS_SOURCE_TAG
    if "local_demo" in joined or "ownerbot_demo" in joined:
        return DEMO_SOURCE_TAG
    return None


def format_tool_response(resp: ToolResponse, *, source_tag: str | None = None) -> str:
    if resp.status == "error" and resp.error:
        return f"❌ Ошибка: {resp.error.code}\n{resp.error.message}"

    lines = []
    resolved_source = source_tag or detect_source_tag(resp)
    if resolved_source:
        lines.append(f"Источник: {resolved_source}")
    
    # Use smart presenter for data
    if resp.data:
        title, body = detect_and_format(resp.data)
        if title:
            lines.append(f"✅ {title}")
        lines.append("")
        lines.append(body)
    else:
        lines.append("✅ Выполнено")

    if resp.warnings:
        lines.append("\n⚠️ Предупреждения:")
        for warning in resp.warnings:
            lines.append(f"• {warning.code}: {warning.message}")

    return "\n".join(lines)


# ============================================================================
# PAGINATED RESPONSE
# ============================================================================

PAGE_SIZE = 5  # Items per page


def _extract_list_data(data: dict[str, Any]) -> tuple[str | None, list[dict] | None]:
    """Extract data type and items list from response data.
    
    Returns: (data_type, items) or (None, None) if not a list response
    """
    if not data:
        return None, None
    
    # Chats
    if "threads" in data:
        return "chats", data["threads"]
    
    # Errors
    if "events" in data:
        return "errors", data["events"]
    
    # Orders (check applied_filters)
    applied_filters = data.get("applied_filters", {})
    if isinstance(applied_filters, dict) and "items" in data:
        preset = applied_filters.get("preset", "")
        status = applied_filters.get("status", "")
        
        if preset == "payment_issues" or "failed" in str(applied_filters):
            return "payment_issues", data["items"]
        if status == "stuck" or preset == "stuck":
            return "stuck_orders", data["items"]
        return "orders", data["items"]
    
    # Items without applied_filters
    if "items" in data and isinstance(data["items"], list):
        items = data["items"]
        if items and isinstance(items[0], dict):
            if items[0].get("status") == "stuck":
                return "stuck_orders", items
            if "order_id" in items[0]:
                return "orders", items
    
    return None, None


async def format_tool_response_paginated(
    resp: ToolResponse,
    *,
    source_tag: str | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Format tool response with pagination support.
    
    Returns: (text, keyboard) where keyboard may be None only for errors
    """
    if resp.status == "error" and resp.error:
        return f"❌ Ошибка: {resp.error.code}\n{resp.error.message}", None
    
    resolved_source = source_tag or detect_source_tag(resp)
    source_line = f"Источник: {resolved_source}\n" if resolved_source else ""
    
    # Check if this is a list response that needs pagination
    data_type, items = _extract_list_data(resp.data)
    
    if data_type and items:
        total = len(items)
        
        if total > PAGE_SIZE:
            # Use pagination with navigation
            session_id = await store_paginated_data(data_type, items, PAGE_SIZE)
            
            total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
            page_items = get_page_items(items, 0, PAGE_SIZE)
            title = get_title_for_type(data_type)
            
            body = format_page(
                data_type=data_type,
                items=page_items,
                page=0,
                total_pages=total_pages,
                total_items=total,
                title=title,
            )
            
            keyboard = build_pagination_keyboard(session_id, 0, total_pages, total)
            text = f"{source_line}✅ {title}\n\n{body}"
            return text, keyboard
        else:
            # No navigation needed, but still add Close button
            session_id = await store_paginated_data(data_type, items, PAGE_SIZE)
            title = get_title_for_type(data_type)
            
            body = format_page(
                data_type=data_type,
                items=items,
                page=0,
                total_pages=1,
                total_items=total,
                title=title,
            )
            
            # Just close button, no navigation
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✖️ Закрыть", callback_data=f"pg:{session_id}:close")]
            ])
            text = f"{source_line}✅ {title}\n\n{body}"
            return text, keyboard
    
    # No list data - use simple format with close button
    text = format_tool_response(resp, source_tag=source_tag)
    
    # Add close button for any response with data
    if resp.data:
        session_id = await store_paginated_data("generic", [], PAGE_SIZE)  # Empty, just for close
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✖️ Закрыть", callback_data=f"pg:{session_id}:close")]
        ])
        return text, keyboard
    
    return text, None


def format_start_message(status: dict) -> str:
    return (
        "OwnerBot online.\n\n"
        f"DB: {'ok' if status.get('db_ok') else 'fail'}\n"
        f"Redis: {'ok' if status.get('redis_ok') else 'fail'}\n"
        f"Owner IDs: {status.get('owner_ids_text', 'none')}\n"
        f"Upstream: configured={status.get('configured_mode', 'unknown')}, effective={status.get('effective_mode', 'unknown')}\n"
        f"ASR={status.get('asr_provider', 'unknown')} | LLM={status.get('llm_provider', 'unknown')}\n"
        "Подробнее: /systems\n\n"
        "Примеры:\n"
        "• дай KPI за вчера\n"
        "• что с заказами, что зависло\n"
        "• /trend 14\n"
        "• график выручки 7 дней\n"
        "• /weekly_pdf\n"
        "• флагни заказ OB-1003 причина тест\n"
        "• /notify Проверь зависшие заказы и ответь клиентам\n"
        "• уведомь команду: проверь OB-1003, завис\n"
    )


def format_tools_list(tools: list[ToolDefinition]) -> str:
    lines = ["Инструменты:"]
    for tool in tools:
        status = "заглушка" if tool.is_stub else "ок"
        lines.append(f"• {tool.name} v{tool.version} ({status})")
    return "\n".join(lines)
