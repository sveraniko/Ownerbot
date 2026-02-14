from __future__ import annotations

import json
import re
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

from app.actions.confirm_flow import create_confirm_token
from app.bot.keyboards.confirm import confirm_keyboard, confirm_keyboard_with_force
from app.bot.services.action_force import requires_force_confirm
from app.bot.services.tool_runner import run_tool
from app.bot.ui.templates_keyboards import (
    build_templates_discounts_keyboard,
    build_templates_looks_keyboard,
    build_templates_main_keyboard,
    build_templates_prices_keyboard,
    build_templates_products_keyboard,
)
from app.bot.ui.formatting import detect_source_tag, format_tool_response
from app.core.contracts import CANCEL_CB_PREFIX, CONFIRM_CB_PREFIX
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolTenant
from app.tools.providers.sis_gateway import upstream_unavailable
from app.tools.registry_setup import build_registry
from app.upstream.selector import choose_data_mode, resolve_effective_mode

router = Router()
registry = build_registry()

_STATE_KEY = "ownerbot:templates:state:"
_MAX_IDS = 200


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=c) for t, c in row] for row in rows]
    )


def _parse_ids(text: str) -> list[str]:
    ids = [item.strip() for item in re.split(r"[\s,]+", text) if item.strip()]
    if not ids:
        raise ValueError("Нужно передать хотя бы один ID.")
    if len(ids) > _MAX_IDS:
        raise ValueError(f"Слишком много ID: максимум {_MAX_IDS}.")
    return ids


def _parse_percent(text: str) -> int:
    value = int(text.strip())
    if value < 1 or value > 95:
        raise ValueError("Процент скидки должен быть от 1 до 95.")
    return value


def _parse_stock_threshold(text: str) -> int:
    value = int(text.strip())
    if value < 1 or value > 9999:
        raise ValueError("N должен быть в диапазоне 1..9999.")
    return value


async def _set_state(user_id: int, state: dict) -> None:
    redis = await get_redis()
    await redis.set(f"{_STATE_KEY}{user_id}", json.dumps(state), ex=900)


async def _get_state(user_id: int) -> dict | None:
    redis = await get_redis()
    raw = await redis.get(f"{_STATE_KEY}{user_id}")
    if not raw:
        return None
    return json.loads(raw)


async def _clear_state(user_id: int) -> None:
    redis = await get_redis()
    await redis.delete(f"{_STATE_KEY}{user_id}")


@router.message(Command("templates"))
async def cmd_templates(message: Message) -> None:
    await message.answer("Шаблоны", reply_markup=build_templates_main_keyboard())


@router.callback_query(F.data == "tpl:prices")
async def tpl_prices(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text(
        "Шаблоны → Цены",
        reply_markup=build_templates_prices_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(F.data == "tpl:products")
async def tpl_products(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text(
        "Шаблоны → Товары",
        reply_markup=build_templates_products_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(F.data == "tpl:looks")
async def tpl_looks(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text(
        "Шаблоны → Товары → Луки",
        reply_markup=build_templates_looks_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(F.data == "tpl:discounts")
async def tpl_discounts(callback_query: CallbackQuery) -> None:
    await callback_query.message.edit_text(
        "Шаблоны → Скидки",
        reply_markup=build_templates_discounts_keyboard(),
    )
    await callback_query.answer()


@router.callback_query(F.data == "tpl:products:publish:ids")
async def tpl_products_publish_ids(callback_query: CallbackQuery) -> None:
    await _set_state(callback_query.from_user.id, {"tool": "sis_products_publish", "step": "product_ids", "payload": {"target_status": "ACTIVE", "dry_run": True}})
    await callback_query.message.edit_text("Введи ID товаров через запятую/пробел/перенос.")
    await callback_query.answer()


@router.callback_query(F.data == "tpl:products:archive:ids")
async def tpl_products_archive_ids(callback_query: CallbackQuery) -> None:
    await _set_state(callback_query.from_user.id, {"tool": "sis_products_publish", "step": "product_ids", "payload": {"target_status": "ARCHIVED", "dry_run": True}})
    await callback_query.message.edit_text("Введи ID товаров через запятую/пробел/перенос.")
    await callback_query.answer()


@router.callback_query(F.data == "tpl:products:publish:all")
async def tpl_products_publish_all(callback_query: CallbackQuery) -> None:
    await _run_template_action(callback_query.message, callback_query.from_user.id, "sis_products_publish", {"status_from": "ARCHIVED", "target_status": "ACTIVE", "dry_run": True})
    await callback_query.answer()


@router.callback_query(F.data == "tpl:products:archive:all")
async def tpl_products_archive_all(callback_query: CallbackQuery) -> None:
    await _run_template_action(callback_query.message, callback_query.from_user.id, "sis_products_publish", {"status_from": "ACTIVE", "target_status": "ARCHIVED", "dry_run": True})
    await callback_query.answer()


@router.callback_query(F.data == "tpl:looks:publish:ids")
async def tpl_looks_publish_ids(callback_query: CallbackQuery) -> None:
    await _set_state(callback_query.from_user.id, {"tool": "sis_looks_publish", "step": "look_ids", "payload": {"target_active": True, "dry_run": True}})
    await callback_query.message.edit_text("Введи ID луков через запятую/пробел/перенос.")
    await callback_query.answer()


@router.callback_query(F.data == "tpl:looks:archive:ids")
async def tpl_looks_archive_ids(callback_query: CallbackQuery) -> None:
    await _set_state(callback_query.from_user.id, {"tool": "sis_looks_publish", "step": "look_ids", "payload": {"target_active": False, "dry_run": True}})
    await callback_query.message.edit_text("Введи ID луков через запятую/пробел/перенос.")
    await callback_query.answer()


@router.callback_query(F.data == "tpl:looks:publish:all")
async def tpl_looks_publish_all(callback_query: CallbackQuery) -> None:
    await _run_template_action(callback_query.message, callback_query.from_user.id, "sis_looks_publish", {"is_active_from": False, "target_active": True, "dry_run": True})
    await callback_query.answer()


@router.callback_query(F.data == "tpl:looks:archive:all")
async def tpl_looks_archive_all(callback_query: CallbackQuery) -> None:
    await _run_template_action(callback_query.message, callback_query.from_user.id, "sis_looks_publish", {"is_active_from": True, "target_active": False, "dry_run": True})
    await callback_query.answer()


@router.callback_query(F.data == "tpl:discounts:clear:ids")
async def tpl_discounts_clear_ids(callback_query: CallbackQuery) -> None:
    await _set_state(callback_query.from_user.id, {"tool": "sis_discounts_clear", "step": "product_ids", "payload": {"dry_run": True}})
    await callback_query.message.edit_text("Введи ID товаров для удаления скидок.")
    await callback_query.answer()


@router.callback_query(F.data == "tpl:discounts:clear:all")
async def tpl_discounts_clear_all(callback_query: CallbackQuery) -> None:
    await _run_template_action(callback_query.message, callback_query.from_user.id, "sis_discounts_clear", {"dry_run": True})
    await callback_query.answer()


@router.callback_query(F.data == "tpl:discounts:set:ids")
async def tpl_discounts_set_ids(callback_query: CallbackQuery) -> None:
    await _set_state(callback_query.from_user.id, {"tool": "sis_discounts_set", "step": "product_ids", "payload": {"dry_run": True}})
    await callback_query.message.edit_text("Введи ID товаров для скидки.")
    await callback_query.answer()


@router.callback_query(F.data == "tpl:discounts:set:stock")
async def tpl_discounts_set_stock(callback_query: CallbackQuery) -> None:
    await _set_state(callback_query.from_user.id, {"tool": "sis_discounts_set", "step": "stock_lte", "payload": {"dry_run": True}})
    await callback_query.message.edit_text("Введи N (остаток <= N), затем бот спросит процент.")
    await callback_query.answer()


@router.callback_query(F.data == "tpl:prices:bump")
async def tpl_bump(callback_query: CallbackQuery) -> None:
    await _set_state(callback_query.from_user.id, {"tool": "sis_prices_bump", "step": "bump_percent", "payload": {}})
    await callback_query.message.edit_text(
        "Поднять цены на %: выбери кнопку или используй /tpl_bump <число>.",
        reply_markup=_kb([[('+5', 'tpl:set:bump:5'), ('+10', 'tpl:set:bump:10'), ('+15', 'tpl:set:bump:15'), ('+20', 'tpl:set:bump:20')]]),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("tpl:set:bump:"))
async def tpl_bump_preset(callback_query: CallbackQuery) -> None:
    value = callback_query.data.split(":")[-1]
    await _run_template_action(
        callback_query.message,
        callback_query.from_user.id,
        "sis_prices_bump",
        {"bump_percent": value, "bump_additive": "0", "rounding_mode": "CEIL_INT", "dry_run": True},
    )
    await _clear_state(callback_query.from_user.id)
    await callback_query.answer()


@router.callback_query(F.data == "tpl:prices:fx")
async def tpl_fx(callback_query: CallbackQuery) -> None:
    await _set_state(
        callback_query.from_user.id,
        {
            "tool": "sis_fx_reprice",
            "step": "input_currency",
            "payload": {
                "markup_percent": "0",
                "markup_additive": "0",
                "rounding_mode": "CEIL_INT",
                "anomaly_threshold_pct": "25",
            },
        },
    )
    await callback_query.message.edit_text(
        "FX пересчёт: выбери input_currency",
        reply_markup=_kb([[('USD', 'tpl:set:fx:input:USD'), ('EUR', 'tpl:set:fx:input:EUR'), ('UAH', 'tpl:set:fx:input:UAH'), ('PLN', 'tpl:set:fx:input:PLN')]]),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("tpl:set:fx:input:"))
async def tpl_fx_input(callback_query: CallbackQuery) -> None:
    value = callback_query.data.split(":")[-1]
    state = await _get_state(callback_query.from_user.id) or {}
    payload = state.get("payload", {})
    payload["input_currency"] = value
    await _set_state(callback_query.from_user.id, {"tool": "sis_fx_reprice", "step": "shop_currency", "payload": payload})
    await callback_query.message.edit_text(
        "Выбери shop_currency",
        reply_markup=_kb([[('EUR', 'tpl:set:fx:shop:EUR'), ('UAH', 'tpl:set:fx:shop:UAH'), ('USD', 'tpl:set:fx:shop:USD'), ('PLN', 'tpl:set:fx:shop:PLN')]]),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("tpl:set:fx:shop:"))
async def tpl_fx_shop(callback_query: CallbackQuery) -> None:
    value = callback_query.data.split(":")[-1]
    state = await _get_state(callback_query.from_user.id) or {}
    payload = state.get("payload", {})
    payload["shop_currency"] = value
    await _set_state(callback_query.from_user.id, {"tool": "sis_fx_reprice", "step": "rate_set_id", "payload": payload})
    await callback_query.message.edit_text("Введи rate_set_id: команда /tpl_rate_set <hash>")
    await callback_query.answer()


@router.callback_query(F.data == "tpl:prices:rollback")
async def tpl_rollback(callback_query: CallbackQuery) -> None:
    await _run_template_action(callback_query.message, callback_query.from_user.id, "sis_fx_rollback", {"dry_run": True})
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
    await _run_template_action(message, message.from_user.id, "sis_prices_bump", {"bump_percent": raw, "bump_additive": "0", "rounding_mode": "CEIL_INT", "dry_run": True})


@router.message(Command("tpl_rate_set"))
async def tpl_rate_set_input(message: Message) -> None:
    if message.text is None:
        return
    state = await _get_state(message.from_user.id)
    if not state or state.get("tool") != "sis_fx_reprice" or state.get("step") != "rate_set_id":
        await message.answer("Нет активного FX шаблона. Запусти: /templates → Шаблоны → Цены → FX пересчёт цен")
        return
    raw = message.text.replace("/tpl_rate_set", "", 1).strip()
    if not raw:
        await message.answer("Формат: /tpl_rate_set <hash>")
        return
    payload = state.get("payload", {})
    payload["rate_set_id"] = raw
    payload["dry_run"] = True
    await _clear_state(message.from_user.id)
    await _run_template_action(message, message.from_user.id, "sis_fx_reprice", payload)


@router.message(F.text)
async def templates_state_input(message: Message) -> None:
    if message.text is None:
        return
    state = await _get_state(message.from_user.id)
    if not state:
        return

    tool = state.get("tool")
    step = state.get("step")
    payload = state.get("payload", {})
    raw = message.text.strip()

    try:
        if tool in {"sis_products_publish", "sis_discounts_clear", "sis_discounts_set"} and step == "product_ids":
            payload["product_ids"] = _parse_ids(raw)
            if tool == "sis_discounts_set":
                await _set_state(message.from_user.id, {"tool": tool, "step": "discount_percent", "payload": payload})
                await message.answer("Введи процент скидки 1..95")
                return
            await _clear_state(message.from_user.id)
            await _run_template_action(message, message.from_user.id, tool, payload)
            return

        if tool == "sis_looks_publish" and step == "look_ids":
            payload["look_ids"] = _parse_ids(raw)
            await _clear_state(message.from_user.id)
            await _run_template_action(message, message.from_user.id, tool, payload)
            return

        if tool == "sis_discounts_set" and step == "stock_lte":
            payload["stock_lte"] = _parse_stock_threshold(raw)
            await _set_state(message.from_user.id, {"tool": tool, "step": "discount_percent", "payload": payload})
            await message.answer("Введи процент скидки 1..95")
            return

        if tool == "sis_discounts_set" and step == "discount_percent":
            payload["discount_percent"] = _parse_percent(raw)
            await _clear_state(message.from_user.id)
            await _run_template_action(message, message.from_user.id, tool, payload)
            return
    except ValueError as exc:
        await message.answer(str(exc))
        return


async def _run_template_action(message: Message, owner_user_id: int, tool_name: str, payload: dict) -> None:
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

    if payload.get("dry_run") is True and response.status == "ok":
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
