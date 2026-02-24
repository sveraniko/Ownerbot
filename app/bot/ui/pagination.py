"""Pagination system for list responses in OwnerBot.

Stores paginated data in Redis and provides navigation controls.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.redis import get_redis

_PAGINATION_KEY = "ownerbot:pagination:"
_PAGINATION_TTL = 600  # 10 minutes


@dataclass
class PaginatedResult:
    """Result of pagination formatting."""
    text: str
    title: str
    page: int
    total_pages: int
    has_prev: bool
    has_next: bool
    session_id: str


async def store_paginated_data(
    data_type: str,
    items: list[dict[str, Any]],
    page_size: int = 5,
) -> str:
    """Store items in Redis for pagination.
    
    Returns: session_id for retrieving pages
    """
    session_id = str(uuid.uuid4())[:8]
    redis = await get_redis()
    
    payload = {
        "data_type": data_type,
        "items": items,
        "page_size": page_size,
        "total": len(items),
    }
    
    await redis.set(
        f"{_PAGINATION_KEY}{session_id}",
        json.dumps(payload, default=str),
        ex=_PAGINATION_TTL,
    )
    
    return session_id


async def get_paginated_data(session_id: str) -> dict[str, Any] | None:
    """Retrieve stored pagination data."""
    redis = await get_redis()
    raw = await redis.get(f"{_PAGINATION_KEY}{session_id}")
    if not raw:
        return None
    return json.loads(raw)


async def delete_paginated_data(session_id: str) -> None:
    """Delete pagination session."""
    redis = await get_redis()
    await redis.delete(f"{_PAGINATION_KEY}{session_id}")


def get_page_items(items: list, page: int, page_size: int) -> list:
    """Get items for specific page (0-indexed)."""
    start = page * page_size
    end = start + page_size
    return items[start:end]


def build_pagination_keyboard(
    session_id: str,
    page: int,
    total_pages: int,
    total_items: int,
) -> InlineKeyboardMarkup | None:
    """Build pagination navigation keyboard.
    
    Returns None if only 1 page (no navigation needed).
    """
    if total_pages <= 1:
        return None
    
    buttons = []
    row = []
    
    # Previous button
    if page > 0:
        row.append(InlineKeyboardButton(
            text="⬅️ Пред",
            callback_data=f"pg:{session_id}:{page - 1}",
        ))
    
    # Page indicator
    row.append(InlineKeyboardButton(
        text=f"{page + 1}/{total_pages}",
        callback_data="pg:noop",
    ))
    
    # Next button
    if page < total_pages - 1:
        row.append(InlineKeyboardButton(
            text="След ➡️",
            callback_data=f"pg:{session_id}:{page + 1}",
        ))
    
    buttons.append(row)
    
    # Close button
    buttons.append([
        InlineKeyboardButton(
            text="✖️ Закрыть",
            callback_data=f"pg:{session_id}:close",
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ============================================================================
# FORMATTERS WITH PAGINATION SUPPORT
# ============================================================================

from datetime import datetime


def _parse_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return None


def _format_datetime(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m в %H:%M")


def _format_hours_ago(dt: datetime | None) -> str:
    if not dt:
        return "—"
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = now - dt
    hours = int(delta.total_seconds() / 3600)
    if hours < 1:
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes} мин"
    if hours < 24:
        return f"{hours} ч"
    days = hours // 24
    return f"{days} дн"


def _translate_status(status: str | None) -> str:
    translations = {
        "pending": "ожидает",
        "paid": "оплачен",
        "failed": "ошибка",
        "stuck": "завис",
        "shipped": "отправлен",
        "delivered": "доставлен",
        "cancelled": "отменён",
        "refunded": "возврат",
    }
    return translations.get(status or "", status or "—")


def format_chat_item(item: dict) -> str:
    """Format single chat item."""
    thread_id = item.get("thread_id", "—")
    customer = item.get("customer_id", "—")
    last_msg = _parse_datetime(item.get("last_customer_message_at"))
    last_reply = _parse_datetime(item.get("last_manager_reply_at"))
    wait_time = _format_hours_ago(last_msg)
    
    lines = [
        f"📨 {thread_id}",
        f"   Клиент: {customer}",
        f"   Сообщение: {_format_datetime(last_msg)}",
    ]
    if last_reply:
        lines.append(f"   Ответ: {_format_datetime(last_reply)}")
    lines.append(f"   Ждёт: {wait_time}")
    return "\n".join(lines)


def format_order_item(item: dict, show_payment: bool = True) -> str:
    """Format single order item."""
    order_id = item.get("order_id", "—")
    amount = item.get("amount", 0)
    currency = item.get("currency", "EUR")
    status = _translate_status(item.get("status"))
    payment_status = _translate_status(item.get("payment_status"))
    created = _parse_datetime(item.get("created_at"))
    age = _format_hours_ago(created)
    
    lines = [
        f"🧾 {order_id}",
        f"   Сумма: {amount} {currency}",
    ]
    if show_payment:
        lines.append(f"   Статус: {status}")
        lines.append(f"   Оплата: {payment_status}")
    else:
        lines.append(f"   Статус: {status} / Оплата: {payment_status}")
    lines.append(f"   Создан: {_format_datetime(created)} ({age} назад)")
    return "\n".join(lines)


def format_error_item(item: dict) -> str:
    """Format single error item."""
    event_type = item.get("event_type", "—")
    occurred = _parse_datetime(item.get("occurred_at"))
    preview = item.get("payload_preview", "")[:80]
    
    lines = [
        f"❌ {event_type}",
        f"   Время: {_format_datetime(occurred)}",
    ]
    if preview:
        lines.append(f"   Детали: {preview}")
    return "\n".join(lines)


def format_product_item(item: dict) -> str:
    """Format single product item."""
    product_id = item.get("product_id", "—")
    title = item.get("title", "—")[:25]
    stock = item.get("stock_qty", "?")
    price = item.get("price", "?")
    
    return f"📦 {product_id}: {title}\n   Остаток: {stock}, Цена: {price}"


# Item formatter registry
ITEM_FORMATTERS = {
    "chats": format_chat_item,
    "orders": format_order_item,
    "payment_issues": format_order_item,
    "stuck_orders": lambda x: format_order_item(x, show_payment=False),
    "errors": format_error_item,
    "products": format_product_item,
}


def format_page(
    data_type: str,
    items: list[dict],
    page: int,
    total_pages: int,
    total_items: int,
    title: str,
) -> str:
    """Format a single page of items."""
    formatter = ITEM_FORMATTERS.get(data_type, lambda x: str(x))
    
    lines = [f"{title}: {total_items}"]
    if total_pages > 1:
        lines[0] += f" (стр. {page + 1}/{total_pages})"
    lines.append("")
    
    for item in items:
        lines.append(formatter(item))
        lines.append("")
    
    return "\n".join(lines).strip()


# ============================================================================
# DATA TYPE TITLES
# ============================================================================

DATA_TYPE_TITLES = {
    "chats": "💬 Чаты без ответа",
    "orders": "🧾 Заказы",
    "payment_issues": "💳 Проблемы с оплатой",
    "stuck_orders": "⏳ Зависшие заказы",
    "errors": "⚠️ Последние ошибки",
    "products": "📦 Товары",
    "inventory": "📦 Статус каталога",
}


def get_title_for_type(data_type: str) -> str:
    """Get human-readable title for data type."""
    return DATA_TYPE_TITLES.get(data_type, data_type)
