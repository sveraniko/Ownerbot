"""Human-readable presenters for different data types.

Each presenter takes raw tool response data and returns formatted text.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _parse_datetime(dt_str: str | None) -> datetime | None:
    """Parse ISO datetime string."""
    if not dt_str:
        return None
    try:
        # Handle timezone suffix
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return None


def _format_datetime(dt: datetime | None) -> str:
    """Format datetime as 'DD.MM в HH:MM'."""
    if not dt:
        return "—"
    return dt.strftime("%d.%m в %H:%M")


def _format_hours_ago(dt: datetime | None) -> str:
    """Calculate hours since datetime."""
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
    """Translate order/payment status to Russian."""
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


# ============================================================================
# CHATS
# ============================================================================

def format_unanswered_chats(data: dict[str, Any]) -> str:
    """Format unanswered chats data."""
    threads = data.get("threads", [])
    count = data.get("count", len(threads))
    threshold = data.get("threshold_hours", 0)
    
    lines = [f"💬 Чаты без ответа: {count}"]
    if threshold:
        lines[0] += f" (>{threshold}ч)"
    lines.append("")
    
    if not threads:
        lines.append("Нет чатов, ожидающих ответа.")
        return "\n".join(lines)
    
    for thread in threads[:10]:  # Limit display
        thread_id = thread.get("thread_id", "—")
        customer = thread.get("customer_id", "—")
        last_msg = _parse_datetime(thread.get("last_customer_message_at"))
        last_reply = _parse_datetime(thread.get("last_manager_reply_at"))
        
        wait_time = _format_hours_ago(last_msg)
        
        lines.append(f"📨 {thread_id}")
        lines.append(f"   Клиент: {customer}")
        lines.append(f"   Сообщение: {_format_datetime(last_msg)}")
        if last_reply:
            lines.append(f"   Ответ: {_format_datetime(last_reply)}")
        lines.append(f"   Ждёт: {wait_time}")
        lines.append("")
    
    if len(threads) > 10:
        lines.append(f"... и ещё {len(threads) - 10}")
    
    return "\n".join(lines)


# ============================================================================
# ORDERS
# ============================================================================

def format_payment_issues(data: dict[str, Any]) -> str:
    """Format payment issues data."""
    items = data.get("items", [])
    count = data.get("count", len(items))
    
    lines = [f"💳 Проблемы с оплатой: {count}"]
    lines.append("")
    
    if not items:
        lines.append("Нет проблем с оплатой.")
        return "\n".join(lines)
    
    for order in items[:10]:
        order_id = order.get("order_id", "—")
        amount = order.get("amount", 0)
        currency = order.get("currency", "EUR")
        status = _translate_status(order.get("status"))
        payment_status = _translate_status(order.get("payment_status"))
        created = _parse_datetime(order.get("created_at"))
        
        lines.append(f"🧾 {order_id}")
        lines.append(f"   Сумма: {amount} {currency}")
        lines.append(f"   Статус: {status}")
        lines.append(f"   Оплата: {payment_status}")
        lines.append(f"   Создан: {_format_datetime(created)}")
        lines.append("")
    
    if len(items) > 10:
        lines.append(f"... и ещё {len(items) - 10}")
    
    return "\n".join(lines)


def format_stuck_orders(data: dict[str, Any]) -> str:
    """Format stuck orders data."""
    items = data.get("items", [])
    count = data.get("count", len(items))
    
    lines = [f"⏳ Зависшие заказы: {count}"]
    lines.append("")
    
    if not items:
        lines.append("Нет зависших заказов.")
        return "\n".join(lines)
    
    for order in items[:10]:
        order_id = order.get("order_id", "—")
        amount = order.get("amount", 0)
        currency = order.get("currency", "EUR")
        status = _translate_status(order.get("status"))
        payment_status = _translate_status(order.get("payment_status"))
        created = _parse_datetime(order.get("created_at"))
        age = _format_hours_ago(created)
        
        lines.append(f"🧾 {order_id}")
        lines.append(f"   Сумма: {amount} {currency}")
        lines.append(f"   Статус: {status} / Оплата: {payment_status}")
        lines.append(f"   Создан: {_format_datetime(created)} ({age} назад)")
        lines.append("")
    
    if len(items) > 10:
        lines.append(f"... и ещё {len(items) - 10}")
    
    return "\n".join(lines)


# ============================================================================
# ERRORS
# ============================================================================

def format_last_errors(data: dict[str, Any]) -> str:
    """Format last errors data."""
    events = data.get("events", [])
    count = data.get("count", len(events))
    
    lines = [f"⚠️ Последние ошибки: {count}"]
    lines.append("")
    
    if not events:
        lines.append("Ошибок не найдено.")
        return "\n".join(lines)
    
    for event in events[:10]:
        event_type = event.get("event_type", "—")
        occurred = _parse_datetime(event.get("occurred_at"))
        preview = event.get("payload_preview", "")[:100]
        
        lines.append(f"❌ {event_type}")
        lines.append(f"   Время: {_format_datetime(occurred)}")
        if preview:
            lines.append(f"   Детали: {preview}")
        lines.append("")
    
    if len(events) > 10:
        lines.append(f"... и ещё {len(events) - 10}")
    
    return "\n".join(lines)


# ============================================================================
# INVENTORY / CATALOG
# ============================================================================

def format_inventory_status(data: dict[str, Any]) -> str:
    """Format inventory status data."""
    counts = data.get("counts", {})
    
    lines = ["📦 Статус каталога"]
    lines.append("")
    
    # Summary counts
    labels = {
        "out_of_stock": "🔴 Нет в наличии",
        "low_stock": "🟡 Мало на складе",
        "missing_photo": "📷 Без фото",
        "missing_price": "💰 Без цены",
        "missing_video": "🎬 Без видео",
        "return_flags": "🚩 С пометкой возврата",
        "unpublished": "📝 Не опубликовано",
    }
    
    for key, label in labels.items():
        count = counts.get(key, 0)
        if count > 0:
            lines.append(f"{label}: {count}")
    
    if not any(counts.get(k, 0) > 0 for k in labels):
        lines.append("✅ Проблем не обнаружено")
    
    lines.append("")
    
    # Show items from specific sections if present
    for section_key in ["out_of_stock", "low_stock", "missing_photo", "missing_price"]:
        items = data.get(section_key, [])
        if items:
            section_label = labels.get(section_key, section_key)
            lines.append(f"\n{section_label}:")
            for item in items[:5]:
                product_id = item.get("product_id", "—")
                title = item.get("title", "—")[:30]
                stock = item.get("stock_qty", "?")
                price = item.get("price", "?")
                lines.append(f"  • {product_id}: {title} (остаток: {stock}, цена: {price})")
            if len(items) > 5:
                lines.append(f"  ... и ещё {len(items) - 5}")
    
    return "\n".join(lines)


# ============================================================================
# GENERIC FALLBACK
# ============================================================================

def format_generic_data(data: dict[str, Any]) -> str:
    """Format generic data as readable key-value pairs."""
    lines = []
    
    for key, value in data.items():
        # Skip complex nested structures in generic view
        if isinstance(value, (list, dict)) and len(str(value)) > 100:
            if isinstance(value, list):
                lines.append(f"• {key}: [{len(value)} элементов]")
            else:
                lines.append(f"• {key}: {{...}}")
        else:
            lines.append(f"• {key}: {value}")
    
    return "\n".join(lines) if lines else "Нет данных"


# ============================================================================
# FX STATUS
# ============================================================================

def format_fx_status(data: dict[str, Any]) -> str:
    """Format FX status data."""
    status = data.get("status", "—")
    status_ru = "✅ активен" if status == "ok" else "❌ ошибка"
    
    base_currency = data.get("base_currency", "—")
    shop_currency = data.get("shop_currency", "—")
    latest_rate = data.get("latest_rate")
    next_reprice = data.get("next_reprice_in_hours")
    would_apply = data.get("would_apply")
    
    lines = [
        f"💱 FX статус: {status_ru}",
        "",
        f"🌐 Базовая валюта: {base_currency}",
        f"🏪 Валюта магазина: {shop_currency}",
    ]
    
    if latest_rate is not None:
        lines.append(f"📊 Текущий курс: {float(latest_rate):.4f}")
        lines.append(f"   ({base_currency} → {shop_currency})")
    
    if next_reprice is not None:
        lines.append(f"⏰ До пересчёта: {next_reprice} ч")
    
    if would_apply is not None:
        apply_text = "да, требуется" if would_apply else "нет"
        lines.append(f"🔄 Нужен пересчёт: {apply_text}")
    
    return "\n".join(lines)


# ============================================================================
# ROUTER
# ============================================================================

def detect_and_format(data: dict[str, Any]) -> tuple[str | None, str]:
    """Detect data type and format accordingly.
    
    Returns: (title, formatted_body)
    """
    if not data:
        return None, "Нет данных"
    
    # Detect by data structure
    
    # FX Status
    if "base_currency" in data and "shop_currency" in data:
        return "FX статус", format_fx_status(data)
    
    if "threads" in data:
        return "Чаты без ответа", format_unanswered_chats(data)
    
    if "events" in data and any("error" in str(e.get("event_type", "")).lower() or "fail" in str(e.get("event_type", "")).lower() for e in data.get("events", [])):
        return "Последние ошибки", format_last_errors(data)
    
    if "counts" in data and ("out_of_stock" in data or "low_stock" in data or "out_of_stock" in data.get("counts", {})):
        return "Статус каталога", format_inventory_status(data)
    
    # Check applied_filters for order queries
    applied_filters = data.get("applied_filters", {})
    if isinstance(applied_filters, dict):
        preset = applied_filters.get("preset", "")
        status_filter = applied_filters.get("status", "")
        
        if preset == "payment_issues" or "failed" in str(applied_filters):
            return "Проблемы с оплатой", format_payment_issues(data)
        
        if status_filter == "stuck" or preset == "stuck":
            return "Зависшие заказы", format_stuck_orders(data)
    
    # Items list without specific type - generic orders
    if "items" in data and isinstance(data["items"], list):
        items = data["items"]
        if items and "order_id" in items[0]:
            # Check if it looks like stuck orders
            if any(item.get("status") == "stuck" for item in items):
                return "Зависшие заказы", format_stuck_orders(data)
            return "Заказы", format_payment_issues(data)  # Reuse format
    
    # Fallback to generic
    return None, format_generic_data(data)
