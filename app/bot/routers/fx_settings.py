"""FX Settings Panel - Interactive UI for business owners.

No JSON required! Simple button-based configuration.
"""
from __future__ import annotations

import json
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.tools.contracts import ToolActor
from app.tools.impl import sis_fx_settings_update
from app.bot.ui.formatting import format_tool_response, detect_source_tag

router = Router()

_FX_DRAFT_KEY = "ownerbot:fx_settings_draft:"
_FX_DRAFT_TTL = 600  # 10 minutes


# --- Mode labels ---
MODE_LABELS = {
    "manual": "🔧 Вручную",
    "daily": "📅 Ежедневно",
    "interval": "⏱ По интервалу",
}

INTERVAL_OPTIONS = [
    (6, "6 часов"),
    (12, "12 часов"),
    (24, "24 часа"),
    (48, "48 часов"),
]

THRESHOLD_OPTIONS = [
    ("0.5", "0.5%"),
    ("1", "1%"),
    ("2", "2%"),
    ("0", "Отключить"),
]


async def _get_current_settings(correlation_id: str) -> dict[str, Any]:
    """Get current FX settings from SIS or DEMO defaults."""
    settings = get_settings()
    
    if settings.upstream_mode == "DEMO":
        return {
            "reprice_schedule_mode": "manual",
            "reprice_schedule_interval_hours": 12,
            "min_rate_delta_percent": "0.5",
        }
    
    # Call status endpoint to get current settings
    from app.tools.providers.sis_actions_gateway import run_sis_request
    resp = await run_sis_request(
        method="GET",
        path="/fx/status",
        payload=None,
        correlation_id=correlation_id,
        settings=settings,
    )
    if resp.status == "ok":
        return resp.data
    return {}


async def _get_draft(user_id: int) -> dict[str, Any]:
    """Get user's draft settings from Redis."""
    redis = await get_redis()
    raw = await redis.get(f"{_FX_DRAFT_KEY}{user_id}")
    if raw:
        return json.loads(raw)
    return {}


async def _set_draft(user_id: int, draft: dict[str, Any]) -> None:
    """Save user's draft settings to Redis."""
    redis = await get_redis()
    await redis.set(f"{_FX_DRAFT_KEY}{user_id}", json.dumps(draft), ex=_FX_DRAFT_TTL)


async def _clear_draft(user_id: int) -> None:
    """Clear user's draft."""
    redis = await get_redis()
    await redis.delete(f"{_FX_DRAFT_KEY}{user_id}")


def _build_main_keyboard(current: dict, draft: dict) -> InlineKeyboardMarkup:
    """Build main FX settings panel keyboard."""
    # Merge current with draft
    mode = draft.get("reprice_schedule_mode") or current.get("reprice_schedule_mode", "manual")
    interval = draft.get("reprice_schedule_interval_hours") or current.get("reprice_schedule_interval_hours", 12)
    threshold = draft.get("min_rate_delta_percent") or current.get("min_rate_delta_percent", "0.5")
    
    mode_label = MODE_LABELS.get(mode, mode)
    interval_label = f"{interval} ч"
    threshold_label = f"{threshold}%" if threshold and threshold != "0" else "откл."
    
    has_changes = bool(draft)
    
    buttons = [
        [InlineKeyboardButton(text=f"Режим: {mode_label}", callback_data="fx:edit:mode")],
    ]
    
    # Only show interval option if mode is "interval"
    if mode == "interval":
        buttons.append([InlineKeyboardButton(text=f"Интервал: {interval_label}", callback_data="fx:edit:interval")])
    
    buttons.append([InlineKeyboardButton(text=f"Мин. порог: {threshold_label}", callback_data="fx:edit:threshold")])
    
    if has_changes:
        buttons.append([
            InlineKeyboardButton(text="💾 Сохранить", callback_data="fx:save"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="fx:cancel"),
        ])
    
    buttons.append([InlineKeyboardButton(text="🏠 Главная", callback_data="ui:home")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_mode_keyboard() -> InlineKeyboardMarkup:
    """Build mode selection keyboard."""
    buttons = [
        [InlineKeyboardButton(text="🔧 Вручную", callback_data="fx:set:mode:manual")],
        [InlineKeyboardButton(text="📅 Ежедневно", callback_data="fx:set:mode:daily")],
        [InlineKeyboardButton(text="⏱ По интервалу", callback_data="fx:set:mode:interval")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="fx:panel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_interval_keyboard() -> InlineKeyboardMarkup:
    """Build interval selection keyboard."""
    buttons = []
    for hours, label in INTERVAL_OPTIONS:
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"fx:set:interval:{hours}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="fx:panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_threshold_keyboard() -> InlineKeyboardMarkup:
    """Build threshold selection keyboard."""
    buttons = []
    for value, label in THRESHOLD_OPTIONS:
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"fx:set:threshold:{value}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="fx:panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_panel_text(current: dict, draft: dict) -> str:
    """Format panel text with current/draft values."""
    mode = draft.get("reprice_schedule_mode") or current.get("reprice_schedule_mode", "manual")
    interval = draft.get("reprice_schedule_interval_hours") or current.get("reprice_schedule_interval_hours", 12)
    threshold = draft.get("min_rate_delta_percent") or current.get("min_rate_delta_percent", "0.5")
    
    mode_label = MODE_LABELS.get(mode, mode)
    
    lines = [
        "⚙️ FX Настройки",
        "",
        f"Режим: {mode_label}",
    ]
    
    if mode == "interval":
        lines.append(f"Интервал: каждые {interval} часов")
    
    if threshold and threshold != "0":
        lines.append(f"Мин. порог: {threshold}%")
    else:
        lines.append("Мин. порог: отключен")
    
    if draft:
        lines.append("")
        lines.append("⚠️ Есть несохранённые изменения")
    
    return "\n".join(lines)


@router.callback_query(F.data == "fx:panel")
async def fx_panel(callback_query: CallbackQuery) -> None:
    """Show FX settings panel."""
    user_id = callback_query.from_user.id
    correlation_id = get_correlation_id()
    
    current = await _get_current_settings(correlation_id)
    draft = await _get_draft(user_id)
    
    text = _format_panel_text(current, draft)
    keyboard = _build_main_keyboard(current, draft)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data == "fx:edit:mode")
async def fx_edit_mode(callback_query: CallbackQuery) -> None:
    """Show mode selection."""
    text = "Выбери режим пересчёта цен:\n\n• Вручную — только по команде\n• Ежедневно — раз в сутки\n• По интервалу — через заданное время"
    await callback_query.message.edit_text(text, reply_markup=_build_mode_keyboard())
    await callback_query.answer()


@router.callback_query(F.data == "fx:edit:interval")
async def fx_edit_interval(callback_query: CallbackQuery) -> None:
    """Show interval selection."""
    text = "Как часто пересчитывать цены?"
    await callback_query.message.edit_text(text, reply_markup=_build_interval_keyboard())
    await callback_query.answer()


@router.callback_query(F.data == "fx:edit:threshold")
async def fx_edit_threshold(callback_query: CallbackQuery) -> None:
    """Show threshold selection."""
    text = "Минимальное изменение курса для пересчёта:\n\n• Если курс изменился меньше порога — пересчёт пропускается\n• Отключить — пересчитывать всегда"
    await callback_query.message.edit_text(text, reply_markup=_build_threshold_keyboard())
    await callback_query.answer()


@router.callback_query(F.data.startswith("fx:set:mode:"))
async def fx_set_mode(callback_query: CallbackQuery) -> None:
    """Set mode value."""
    mode = callback_query.data.split(":")[-1]
    user_id = callback_query.from_user.id
    
    draft = await _get_draft(user_id)
    draft["reprice_schedule_mode"] = mode
    await _set_draft(user_id, draft)
    
    correlation_id = get_correlation_id()
    current = await _get_current_settings(correlation_id)
    
    text = _format_panel_text(current, draft)
    keyboard = _build_main_keyboard(current, draft)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer(f"Режим: {MODE_LABELS.get(mode, mode)}")


@router.callback_query(F.data.startswith("fx:set:interval:"))
async def fx_set_interval(callback_query: CallbackQuery) -> None:
    """Set interval value."""
    hours = int(callback_query.data.split(":")[-1])
    user_id = callback_query.from_user.id
    
    draft = await _get_draft(user_id)
    draft["reprice_schedule_interval_hours"] = hours
    await _set_draft(user_id, draft)
    
    correlation_id = get_correlation_id()
    current = await _get_current_settings(correlation_id)
    
    text = _format_panel_text(current, draft)
    keyboard = _build_main_keyboard(current, draft)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer(f"Интервал: {hours} ч")


@router.callback_query(F.data.startswith("fx:set:threshold:"))
async def fx_set_threshold(callback_query: CallbackQuery) -> None:
    """Set threshold value."""
    value = callback_query.data.split(":")[-1]
    user_id = callback_query.from_user.id
    
    draft = await _get_draft(user_id)
    draft["min_rate_delta_percent"] = value
    await _set_draft(user_id, draft)
    
    correlation_id = get_correlation_id()
    current = await _get_current_settings(correlation_id)
    
    text = _format_panel_text(current, draft)
    keyboard = _build_main_keyboard(current, draft)
    
    label = f"{value}%" if value != "0" else "откл."
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer(f"Порог: {label}")


@router.callback_query(F.data == "fx:save")
async def fx_save(callback_query: CallbackQuery) -> None:
    """Save FX settings changes."""
    user_id = callback_query.from_user.id
    correlation_id = get_correlation_id()
    
    draft = await _get_draft(user_id)
    if not draft:
        await callback_query.answer("Нет изменений для сохранения", show_alert=True)
        return
    
    # Convert draft to API format
    updates = {}
    if "reprice_schedule_mode" in draft:
        updates["reprice_schedule_mode"] = draft["reprice_schedule_mode"]
    if "reprice_schedule_interval_hours" in draft:
        updates["reprice_schedule_interval_hours"] = draft["reprice_schedule_interval_hours"]
    if "min_rate_delta_percent" in draft:
        updates["min_rate_delta_percent"] = draft["min_rate_delta_percent"]
    
    # Call the update tool
    payload = sis_fx_settings_update.Payload(dry_run=False, updates=updates)
    actor = ToolActor(owner_user_id=user_id)
    
    response = await sis_fx_settings_update.handle(
        payload=payload,
        correlation_id=correlation_id,
        session=None,
        actor=actor,
    )
    
    if response.status == "ok":
        await _clear_draft(user_id)
        
        current = await _get_current_settings(correlation_id)
        text = _format_panel_text(current, {})
        text += "\n\n✅ Настройки сохранены!"
        keyboard = _build_main_keyboard(current, {})
        
        await callback_query.message.edit_text(text, reply_markup=keyboard)
        await callback_query.answer("Сохранено!")
    else:
        error_msg = response.data.get("error", "Неизвестная ошибка") if isinstance(response.data, dict) else "Ошибка"
        await callback_query.answer(f"Ошибка: {error_msg}", show_alert=True)


@router.callback_query(F.data == "fx:cancel")
async def fx_cancel(callback_query: CallbackQuery) -> None:
    """Cancel draft changes."""
    user_id = callback_query.from_user.id
    await _clear_draft(user_id)
    
    correlation_id = get_correlation_id()
    current = await _get_current_settings(correlation_id)
    
    text = _format_panel_text(current, {})
    keyboard = _build_main_keyboard(current, {})
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer("Изменения отменены")
