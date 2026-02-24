"""Pagination callback handlers for OwnerBot."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.ui.pagination import (
    build_pagination_keyboard,
    delete_paginated_data,
    format_page,
    get_page_items,
    get_paginated_data,
    get_title_for_type,
)

router = Router()


@router.callback_query(F.data == "pg:noop")
async def pagination_noop(callback_query: CallbackQuery) -> None:
    """Handle noop callback (page indicator click)."""
    await callback_query.answer()


@router.callback_query(F.data.startswith("pg:") & F.data.endswith(":close"))
async def pagination_close(callback_query: CallbackQuery) -> None:
    """Handle close button - delete message."""
    parts = callback_query.data.split(":")
    if len(parts) >= 2:
        session_id = parts[1]
        await delete_paginated_data(session_id)
    
    await callback_query.message.delete()
    await callback_query.answer()


@router.callback_query(F.data.startswith("pg:"))
async def pagination_navigate(callback_query: CallbackQuery) -> None:
    """Handle pagination navigation (prev/next)."""
    parts = callback_query.data.split(":")
    if len(parts) != 3:
        await callback_query.answer("Ошибка навигации", show_alert=True)
        return
    
    _, session_id, page_str = parts
    
    try:
        page = int(page_str)
    except ValueError:
        await callback_query.answer("Ошибка страницы", show_alert=True)
        return
    
    # Get stored data
    data = await get_paginated_data(session_id)
    if not data:
        await callback_query.answer("Сессия истекла. Запусти запрос заново.", show_alert=True)
        return
    
    items = data["items"]
    page_size = data["page_size"]
    total = data["total"]
    data_type = data["data_type"]
    
    total_pages = (total + page_size - 1) // page_size
    
    # Validate page
    if page < 0 or page >= total_pages:
        await callback_query.answer()
        return
    
    # Get page items
    page_items = get_page_items(items, page, page_size)
    title = get_title_for_type(data_type)
    
    # Format page
    text = format_page(
        data_type=data_type,
        items=page_items,
        page=page,
        total_pages=total_pages,
        total_items=total,
        title=title,
    )
    
    # Build keyboard
    keyboard = build_pagination_keyboard(session_id, page, total_pages, total)
    
    # Update message
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()
