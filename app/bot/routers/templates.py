from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from app.core.time import utcnow

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.actions.confirm_flow import create_confirm_token
from app.bot.keyboards.confirm import confirm_keyboard, confirm_keyboard_with_force
from app.bot.services.action_force import requires_force_confirm
from app.bot.services.action_preview import is_noop_preview
from app.bot.services.tool_runner import run_tool
from app.bot.services.presentation import send_revenue_trend_png, send_weekly_pdf
from app.bot.ui.formatting import detect_source_tag, format_tool_response
from app.bot.ui.templates_keyboards import (
    build_input_presets_keyboard,
    build_templates_category_keyboard,
    build_templates_main_keyboard,
    category_title,
)
from app.core.contracts import CANCEL_CB_PREFIX, CONFIRM_CB_PREFIX
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.templates.catalog import get_template_catalog
from app.templates.catalog.parsers import parse_input_value
from app.tools.contracts import ToolActor, ToolTenant
from app.tools.providers.sis_gateway import upstream_unavailable
from app.tools.registry_setup import build_registry
from app.upstream.selector import choose_data_mode, resolve_effective_mode

router = Router()
registry = build_registry()

_STATE_KEY = "ownerbot:templates:state:"
_STATE_TTL_SECONDS = 900


def _parse_category_page(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != 5 or parts[0] != "tpl" or parts[1] not in {"cat", "back"} or parts[3] != "p":
        return None
    try:
        return parts[2], int(parts[4])
    except ValueError:
        return None


def _parse_preset_callback(data: str) -> tuple[str, int, int] | None:
    parts = data.split(":")
    if len(parts) != 5 or parts[0] != "tpl" or parts[1] != "ps":
        return None
    try:
        return parts[2], int(parts[3]), int(parts[4])
    except ValueError:
        return None


async def _set_state(user_id: int, state: dict) -> None:
    redis = await get_redis()
    await redis.set(f"{_STATE_KEY}{user_id}", json.dumps(state), ex=_STATE_TTL_SECONDS)


async def _get_state(user_id: int) -> dict | None:
    redis = await get_redis()
    raw = await redis.get(f"{_STATE_KEY}{user_id}")
    if not raw:
        return None
    return json.loads(raw)


async def _clear_state(user_id: int) -> None:
    redis = await get_redis()
    await redis.delete(f"{_STATE_KEY}{user_id}")


async def _prompt_current_step(message: Message, template_id: str, step_index: int) -> None:
    spec = get_template_catalog().get(template_id)
    step = spec.inputs[step_index]
    presets = step.presets or []
    if presets:
        markup = build_input_presets_keyboard(template_id, step_index, [(item.text, item.value) for item in presets])
        await message.answer(step.prompt, reply_markup=markup)
        return
    await message.answer(step.prompt)


@router.message(Command("templates"))
async def cmd_templates(message: Message) -> None:
    await _clear_state(message.from_user.id)
    await message.answer("Шаблоны", reply_markup=build_templates_main_keyboard())


@router.callback_query(F.data == "tpl:home")
async def tpl_home(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text("Шаблоны", reply_markup=build_templates_main_keyboard())
    await callback_query.answer()


@router.callback_query(F.data.startswith("tpl:cat:") | F.data.startswith("tpl:back:"))
async def tpl_open_category(callback_query: CallbackQuery) -> None:
    parsed = _parse_category_page(callback_query.data)
    if parsed is None:
        await callback_query.answer()
        return
    category, page = parsed
    await callback_query.message.edit_text(
        f"Шаблоны → {category_title(category)}",
        reply_markup=build_templates_category_keyboard(category, page=page),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("tpl:run:"))
async def tpl_run(callback_query: CallbackQuery) -> None:
    template_id = callback_query.data.split(":", 2)[-1]
    catalog = get_template_catalog()
    try:
        spec = catalog.get(template_id)
    except KeyError:
        await callback_query.answer("Шаблон не найден", show_alert=True)
        return

    payload = dict(spec.default_payload)
    if not spec.inputs:
        payload["dry_run"] = spec.kind == "ACTION"
        await _run_template_action(callback_query.message, callback_query.from_user.id, spec, payload)
        await callback_query.answer()
        return

    await _set_state(
        callback_query.from_user.id,
        {
            "template_id": template_id,
            "step_index": 0,
            "payload_partial": payload,
        },
    )
    await callback_query.answer()
    await _prompt_current_step(callback_query.message, template_id, 0)


@router.callback_query(F.data.startswith("tpl:ps:"))
async def tpl_preset_value(callback_query: CallbackQuery) -> None:
    parsed = _parse_preset_callback(callback_query.data)
    if parsed is None:
        await callback_query.answer()
        return
    template_id, step_index, preset_index = parsed
    catalog = get_template_catalog()
    state = await _get_state(callback_query.from_user.id)
    if not state or state.get("template_id") != template_id or state.get("step_index") != step_index:
        await callback_query.answer("Сессия ввода истекла. Запусти шаблон заново.", show_alert=True)
        return

    spec = catalog.get(template_id)
    step = spec.inputs[step_index]
    presets = step.presets or []
    if preset_index < 0 or preset_index >= len(presets):
        await callback_query.answer()
        return

    await _consume_step_value(callback_query.message, callback_query.from_user.id, spec, step_index, presets[preset_index].value)
    await callback_query.answer()


@router.message(Command("tpl_bump"))
async def tpl_bump_input(message: Message) -> None:
    if message.text is None:
        return
    raw = message.text.replace("/tpl_bump", "", 1).strip()
    if not raw:
        await message.answer("Формат: /tpl_bump 10")
        return
    await _clear_state(message.from_user.id)
    spec = get_template_catalog().get("PRC_BUMP")
    payload = dict(spec.default_payload)
    payload["bump_percent"] = raw
    payload["dry_run"] = True
    await _run_template_action(message, message.from_user.id, spec, payload)


@router.message(Command("tpl_rate_set"))
async def tpl_rate_set_input(message: Message) -> None:
    if message.text is None:
        return
    state = await _get_state(message.from_user.id)
    if not state or state.get("template_id") != "PRC_FX_REPRICE" or state.get("step_index") != 2:
        await message.answer("Нет активного FX шаблона. Запусти: /templates → Шаблоны → Цены → FX пересчёт цен")
        return
    raw = message.text.replace("/tpl_rate_set", "", 1).strip()
    if not raw:
        await message.answer("Формат: /tpl_rate_set <hash>")
        return

    spec = get_template_catalog().get("PRC_FX_REPRICE")
    await _consume_step_value(message, message.from_user.id, spec, 2, raw)


@router.message(F.text)
async def templates_state_input(message: Message) -> None:
    if message.text is None:
        return
    state = await _get_state(message.from_user.id)
    if not state:
        return

    catalog = get_template_catalog()
    template_id = state.get("template_id")
    step_index = state.get("step_index")
    if not isinstance(template_id, str) or not isinstance(step_index, int):
        await _clear_state(message.from_user.id)
        return

    try:
        spec = catalog.get(template_id)
    except KeyError:
        await _clear_state(message.from_user.id)
        return

    await _consume_step_value(message, message.from_user.id, spec, step_index, message.text.strip())


async def _consume_step_value(message: Message, user_id: int, spec, step_index: int, raw_value: str) -> None:
    state = await _get_state(user_id) or {}
    payload = dict(state.get("payload_partial") or spec.default_payload)
    step = spec.inputs[step_index]

    try:
        payload[step.key] = parse_input_value(step.parser, raw_value)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    next_index = step_index + 1
    if next_index < len(spec.inputs):
        await _set_state(
            user_id,
            {
                "template_id": spec.template_id,
                "step_index": next_index,
                "payload_partial": payload,
            },
        )
        await _prompt_current_step(message, spec.template_id, next_index)
        return

    await _clear_state(user_id)
    payload["dry_run"] = spec.kind == "ACTION"
    await _run_template_action(message, user_id, spec, payload)




def _resolve_payload_tokens(value):
    if isinstance(value, dict):
        return {k: _resolve_payload_tokens(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_payload_tokens(v) for v in value]
    if value == "@today":
        return date.today().isoformat()
    if value == "@yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    if value == "@now":
        return utcnow().isoformat()
    return value


async def _run_template_action(message: Message, owner_user_id: int, spec, payload: dict) -> None:
    if isinstance(spec, str):
        tool_name = spec
        presentation = {}
    else:
        tool_name = spec.tool_name
        presentation = spec.presentation or {}
    payload = _resolve_payload_tokens(payload)
    settings = get_settings()
    redis = await get_redis()
    effective_mode, _ = await resolve_effective_mode(settings=settings, redis=redis)
    correlation_id = get_correlation_id()
    actor = ToolActor(owner_user_id=owner_user_id)
    tenant = ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU")

    async def _ping_failover():
        return upstream_unavailable(correlation_id)

    await choose_data_mode(
        effective_mode=effective_mode,
        redis=redis,
        correlation_id=correlation_id,
        ping_callable=_ping_failover,
    )

    if presentation.get("kind") == "weekly_pdf":
        await send_weekly_pdf(
            message=message,
            actor=actor,
            tenant=tenant,
            correlation_id=correlation_id,
            registry=registry,
        )
        return

    response = await run_tool(
        tool_name,
        payload,
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        idempotency_key=str(uuid.uuid4()),
        registry=registry,
    )

    if response.status == "ok" and presentation.get("kind") == "chart_png":
        days = int(presentation.get("days", payload.get("days", 30)))
        title = f"Revenue trend — последние {days} дней"
        await send_revenue_trend_png(
            message=message,
            trend_response=response.data,
            days=days,
            title=title,
            currency=tenant.currency,
            timezone=tenant.timezone,
        )
        return

    if payload.get("dry_run") is True and response.status == "ok":
        if is_noop_preview(response):
            source_tag = detect_source_tag(response)
            await message.answer(format_tool_response(response, source_tag=source_tag))
            return
        payload_commit = dict(payload)
        payload_commit["dry_run"] = False
        confirm_payload = {
            "tool_name": tool_name,
            "payload_commit": payload_commit,
            "owner_user_id": owner_user_id,
            "idempotency_key": str(uuid.uuid4()),
        }
        token = await create_confirm_token(confirm_payload)

        if requires_force_confirm(response):
            force_payload = dict(payload_commit)
            force_payload["force"] = True
            force_token = await create_confirm_token(
                {
                    "tool_name": tool_name,
                    "payload_commit": force_payload,
                    "owner_user_id": owner_user_id,
                    "idempotency_key": str(uuid.uuid4()),
                }
            )
            kb = confirm_keyboard_with_force(
                f"{CONFIRM_CB_PREFIX}{token}",
                f"{CONFIRM_CB_PREFIX}{force_token}",
                f"{CANCEL_CB_PREFIX}{token}",
            )
        else:
            kb = confirm_keyboard(f"{CONFIRM_CB_PREFIX}{token}", f"{CANCEL_CB_PREFIX}{token}")

        source_tag = detect_source_tag(response)
        await message.answer(format_tool_response(response, source_tag=source_tag), reply_markup=kb)
        return

    source_tag = detect_source_tag(response)
    await message.answer(format_tool_response(response, source_tag=source_tag))
