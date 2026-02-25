from __future__ import annotations

import json
import logging
import re
import time
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.actions.confirm_flow import create_confirm_token
from app.actions.capabilities import capability_support_status, get_sis_capabilities, required_capabilities_for_tool
from app.agent_actions.plan_builder import build_plan_from_text
from app.agent_actions.plan_models import PlanIntent, PlanStep
from app.agent_actions.plan_executor import clear_active_plan, execute_plan_preview, get_active_plan
from app.agent_actions.param_coercion import (
    coerce_action_payload,
    parse_hours_value,
    parse_ids_value,
    parse_order_id_value,
    parse_percent_value,
)
from app.asr.audio_convert import convert_ogg_to_wav
from app.asr.cache import get_or_transcribe
from app.asr.errors import ASRError
from app.asr.factory import get_asr_provider
from app.bot.keyboards.confirm import confirm_keyboard, confirm_keyboard_with_force
from app.bot.services.action_force import requires_force_confirm
from app.bot.services.action_preview import is_noop_preview
from app.bot.services.intent_router import route_intent
from app.bot.services.retrospective import write_retrospective_event
from app.bot.services.tool_runner import run_tool
from app.bot.services.presentation import send_revenue_trend_png, send_weekly_pdf
from app.bot.ui.formatting import detect_source_tag, format_tool_response_with_quality
from app.bot.ui.anchor_panel import render_anchor_panel
from app.bot.ui.home_render import render_home_panel
from app.bot.ui.templates_keyboards import (
    build_templates_discounts_keyboard,
    build_templates_main_keyboard,
    build_templates_prices_keyboard,
    build_templates_products_keyboard,
)
from app.core.contracts import CANCEL_CB_PREFIX, CONFIRM_CB_PREFIX
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.core.audit import write_audit_event
from app.advice.advice_cache import load_last_advice, save_last_advice, utc_now_iso
from app.advice.classifier import AdviceTopic, classify_advice_topic
from app.advice.memo_renderer import render_decision_memo_pdf
from app.advice.playbooks import build_playbook
from app.advice.data_brief import (
    DataBriefResult,
    is_cooldown_active,
    load_cached_brief,
    run_tool_set_sequential,
    save_brief_cache,
    select_tool_set,
    set_brief_cooldown,
)
from app.advice.sanitizer import format_advice_text, sanitize_advice_payload, synthesize_advice
from app.llm.router import llm_plan_intent
from app.quality.models import QualityContext
from app.quality.verifier import assess_advice_intent, format_quality_header
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse, ToolTenant
from app.tools.providers.sis_gateway import run_sis_tool, upstream_unavailable
from app.tools.registry_setup import build_registry
from app.upstream.selector import choose_data_mode, resolve_effective_mode
from app.upstream.sis_client import SisClient

router = Router()
logger = logging.getLogger(__name__)
registry = build_registry()
_ADVICE_TOOL_PREFIX = "llm:advice_tool:"
_ADVICE_VALIDATE_PREFIX = "llm:advice_validate:"
_ADVICE_ACTION_PREFIX = "llm:advice_action:"
_ADVICE_BRIEF_REFRESH_PREFIX = "advice:brief:refresh:"
_ADVICE_MEMO_PREFIX = "advice:memo:"
_WIZARD_KEY_PREFIX = "ownerbot:action_wizard:"
_WIZARD_TTL_SECONDS = 900
_WIZARD_CANCEL_CB = "ownerbot:wizard:cancel"
_WIZARD_PRESET_CB = "ownerbot:wizard:preset:"
_CANCEL_WORDS = {"отмена", "cancel", "стоп"}
_PLAN_CANCEL_WORDS = {"отмена", "cancel", "стоп"}


def _looks_like_advice_query(text: str) -> bool:
    lowered = text.lower()
    markers = ("что", "как", "почему", "совет", "стоит ли", "где", "когда")
    return any(marker in lowered for marker in markers) or "?" in text


def _is_data_brief_trigger(text: str) -> bool:
    lowered = text.lower()
    triggers = (
        "на основе наших данных",
        "по нашим данным",
        "по статистике",
        "по данным магазина",
    )
    return any(item in lowered for item in triggers)


async def _build_data_brief(message: Message, topic: AdviceTopic, *, source: str, force_refresh: bool = False) -> DataBriefResult | None:
    chat_id = message.chat.id
    correlation_id = get_correlation_id()
    cached = await load_cached_brief(chat_id, topic)
    if cached is not None and not force_refresh:
        await write_audit_event("advice_data_brief_cache_hit", {"topic": topic.value}, correlation_id=correlation_id)
        return cached
    if force_refresh and await is_cooldown_active(chat_id, topic):
        await write_audit_event("advice_data_brief_refresh_blocked_cooldown", {"topic": topic.value}, correlation_id=correlation_id)
        await message.answer("⏳ Бриф недавно обновляли, подожди 2 минуты.")
        return cached
    if cached is None and await is_cooldown_active(chat_id, topic):
        await write_audit_event("advice_data_brief_refresh_blocked_cooldown", {"topic": topic.value}, correlation_id=correlation_id)
        await message.answer("⏳ Подожди 2 минуты перед следующим сбором брифа.")
        return None

    calls = select_tool_set(topic)
    await write_audit_event("advice_data_brief_requested", {"topic": topic.value, "source": source}, correlation_id=correlation_id)

    async def _runner(tool_name: str, payload: dict) -> ToolResponse:
        tool_def = registry.get(tool_name)
        if tool_def is None or tool_def.kind == "action":
            return ToolResponse.fail(correlation_id=correlation_id, code="REPORT_ONLY_ENFORCED", message="Data Brief can run REPORT tools only.")
        return await run_tool(
            tool_name,
            payload,
            message=message,
            actor=ToolActor(owner_user_id=message.from_user.id),
            tenant=ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
            correlation_id=correlation_id,
            registry=registry,
            intent_source="RULE",
        )

    brief = await run_tool_set_sequential(topic=topic, tool_runner=_runner, calls=calls)
    await save_brief_cache(chat_id, brief)
    await set_brief_cooldown(chat_id, topic)
    ok_count = sum(1 for item in brief.tools_run if item.get("ok"))
    warnings_count = sum(int(item.get("warnings_count") or 0) for item in brief.tools_run)
    await write_audit_event(
        "advice_data_brief_built",
        {"topic": topic.value, "tools_count": len(brief.tools_run), "ok_count": ok_count, "warnings_count": warnings_count},
        correlation_id=correlation_id,
    )
    return brief

_WIZARD_QUESTIONS: dict[str, dict[str, dict[str, object]]] = {
    "create_coupon": {
        "размер скидки в %": {"text": "Сколько процентов скидка? (например 10)", "presets": ["5", "10", "15", "20"]},
        "срок действия в часах": {"text": "На сколько часов? (24/48/72)", "presets": ["24", "48", "72"]},
    },
    "sis_prices_bump": {
        "процент изменения цены": {"text": "На сколько процентов изменить цену?", "presets": ["3", "5", "10"]},
    },
    "notify_team": {
        "сообщение для менеджера": {"text": "Что передать менеджеру?"},
    },
    "sis_products_publish": {
        "список product_ids": {"text": "ID товаров через запятую"},
    },
    "sis_looks_publish": {
        "список look_ids": {"text": "ID луков через запятую"},
    },
}


def _wizard_key(chat_id: int) -> str:
    return f"{_WIZARD_KEY_PREFIX}{chat_id}"


async def _get_wizard_state(chat_id: int) -> dict | None:
    try:
        redis = await get_redis()
        raw = await redis.get(_wizard_key(chat_id))
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def _set_wizard_state(chat_id: int, state: dict) -> None:
    redis = await get_redis()
    await redis.set(_wizard_key(chat_id), json.dumps(state), ex=_WIZARD_TTL_SECONDS)


async def _clear_wizard_state(chat_id: int) -> None:
    try:
        redis = await get_redis()
        await redis.delete(_wizard_key(chat_id))
    except Exception:
        return


def _wizard_markup(config: dict[str, object]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    presets = config.get("presets") if isinstance(config, dict) else None
    if isinstance(presets, list) and presets:
        rows.append([InlineKeyboardButton(text=str(item), callback_data=f"{_WIZARD_PRESET_CB}{item}") for item in presets[:4]])
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data=_WIZARD_CANCEL_CB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _plan_confirm_markup(confirm_cb_data: str, only_main_cb_data: str, cancel_cb_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнить всё", callback_data=confirm_cb_data)],
            [InlineKeyboardButton(text="✅ Выполнить только основной шаг", callback_data=only_main_cb_data)],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data=cancel_cb_data)],
        ]
    )


async def _render_wizard_prompt(message: Message, tool_name: str, field_name: str) -> None:
    config = _WIZARD_QUESTIONS.get(tool_name, {}).get(field_name, {"text": f"Уточни: {field_name}"})
    await render_anchor_panel(message, text=str(config.get("text", f"Уточни: {field_name}")), reply_markup=_wizard_markup(config))


def _parse_wizard_field(field_name: str, text: str) -> dict:
    if field_name in {"размер скидки в %", "процент изменения цены"}:
        value = parse_percent_value(text)
        if value is None:
            return {}
        if field_name == "размер скидки в %":
            return {"percent_off": abs(value)}
        return {"value": value}
    if field_name == "срок действия в часах":
        value = parse_hours_value(text)
        return {"hours_valid": value} if value is not None else {}
    if field_name in {"список product_ids", "список look_ids"}:
        ids = parse_ids_value(text)
        if not ids:
            return {}
        return {"product_ids": ids} if "product" in field_name else {"look_ids": ids}
    if field_name == "сообщение для менеджера":
        cleaned = text.strip()
        return {"message": cleaned} if cleaned else {}
    if field_name == "номер заказа":
        order_id = parse_order_id_value(text)
        return {"order_id": order_id} if order_id else {}
    return {}


async def _start_wizard(message: Message, *, tool_name: str, payload_partial: dict, missing_fields: tuple[str, ...], source: str, correlation_id: str, plan_context: dict | None = None) -> None:
    if not getattr(message, "chat", None):
        await message.answer(f"Нужно уточнить: {', '.join(missing_fields)}.")
        return
    state = {
        "tool_name": tool_name,
        "payload_partial": payload_partial,
        "missing_fields": list(missing_fields),
        "step_index": 0,
        "created_at": int(time.time()),
        "source": source,
        "correlation_id": correlation_id,
    }
    if plan_context is not None:
        state["plan_context"] = plan_context
    await _set_wizard_state(message.chat.id, state)
    await write_audit_event("agent_action_wizard_started", {"tool_name": tool_name, "missing_fields": list(missing_fields)}, correlation_id=correlation_id)
    field_name = missing_fields[0]
    await write_audit_event("agent_action_wizard_step", {"field_name": field_name}, correlation_id=correlation_id)
    await _render_wizard_prompt(message, tool_name, field_name)


async def _cancel_wizard(message: Message, *, correlation_id: str) -> None:
    await _clear_wizard_state(message.chat.id)
    await write_audit_event("agent_action_wizard_cancelled", {}, correlation_id=correlation_id)
    await message.answer("Ок, отменил.")
    await render_home_panel(message)


async def _handle_existing_wizard(message: Message, text: str) -> bool:
    if not getattr(message, "chat", None):
        return False
    state = await _get_wizard_state(message.chat.id)
    if state is None:
        return False
    if text.startswith("/"):
        return False
    correlation_id = get_correlation_id()
    if text.lower().strip() in _CANCEL_WORDS:
        await _cancel_wizard(message, correlation_id=correlation_id)
        return True
    missing_fields = list(state.get("missing_fields") or [])
    step_index = int(state.get("step_index") or 0)
    if step_index >= len(missing_fields):
        await _clear_wizard_state(message.chat.id)
        await message.answer("Контекст устарел. Повтори команду.")
        return True
    field_name = str(missing_fields[step_index])
    parsed = _parse_wizard_field(field_name, text)
    if not parsed:
        await _render_wizard_prompt(message, str(state.get("tool_name") or ""), field_name)
        return True
    payload_partial = dict(state.get("payload_partial") or {})
    payload_partial.update(parsed)
    step_index += 1
    if step_index < len(missing_fields):
        state["payload_partial"] = payload_partial
        state["step_index"] = step_index
        await _set_wizard_state(message.chat.id, state)
        next_field = str(missing_fields[step_index])
        await write_audit_event("agent_action_wizard_step", {"field_name": next_field}, correlation_id=correlation_id)
        await _render_wizard_prompt(message, str(state.get("tool_name") or ""), next_field)
        return True
    await _clear_wizard_state(message.chat.id)
    await write_audit_event("agent_action_wizard_completed", {"tool_name": state.get("tool_name")}, correlation_id=correlation_id)
    plan_context = state.get("plan_context")
    if isinstance(plan_context, dict) and plan_context.get("plan"):
        plan_raw = dict(plan_context.get("plan") or {})
        step_id = str(plan_context.get("step_id") or "s1")
        for step in plan_raw.get("steps", []):
            if str(step.get("step_id")) == step_id:
                payload = dict(step.get("payload") or {})
                payload.update(payload_partial)
                step["payload"] = payload
                break
        plan = PlanIntent.model_validate(plan_raw)
        plan_result = await execute_plan_preview(
            plan,
            {
                "settings": get_settings(),
                "correlation_id": correlation_id,
                "message": message,
                "chat_id": message.chat.id,
                "actor": ToolActor(owner_user_id=message.from_user.id),
                "tenant": ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        formatted_text, _ = format_tool_response_with_quality(plan_result.response, intent_source=plan.source if plan.source == "LLM" else "RULE", tool_name=plan.steps[0].tool_name)
        preview_text = f"{formatted_text}\n\n{plan_result.preview_text}"
        markup = None
        if plan_result.confirm_needed and plan_result.confirm_cb_data and plan_result.confirm_only_main_cb_data and plan_result.cancel_cb_data:
            markup = _plan_confirm_markup(plan_result.confirm_cb_data, plan_result.confirm_only_main_cb_data, plan_result.cancel_cb_data)
        await message.answer(preview_text, reply_markup=markup)
        return
    await handle_tool_call(
        message,
        text,
        input_kind="wizard",
        prebuilt_intent={
            "tool": state.get("tool_name"),
            "payload": payload_partial,
            "source": state.get("source", "LLM"),
        },
    )
    return True


async def _save_last_advice_context(
    message: Message,
    *,
    topic: AdviceTopic | None,
    question_text: str,
    advice_text: str,
    synthesized,
) -> None:
    payload = {
        "topic": topic.value if isinstance(topic, AdviceTopic) and topic != AdviceTopic.NONE else AdviceTopic.NONE.value,
        "question_text": question_text[:240],
        "advice_text": advice_text[:4000],
        "hypotheses": [str(item) for item in list(getattr(synthesized, "bullets", []) or [])[:7]],
        "risks": [str(item) for item in list(getattr(synthesized, "risks", []) or [])[:3]],
        "experiments": [str(item) for item in list(getattr(synthesized, "experiments", []) or [])[:6]],
        "suggested_actions": [item.model_dump() for item in list(getattr(synthesized, "suggested_actions", []) or [])[:3]],
        "created_at": utc_now_iso(),
    }
    try:
        await save_last_advice(message.chat.id, payload)
    except Exception:
        return


async def _store_advice_bundle(
    owner_user_id: int,
    *,
    suggested_tools: list[dict],
    suggested_actions: list[dict],
    topic: AdviceTopic | None = None,
    has_brief: bool = False,
    brief_tools: list[str] | None = None,
) -> tuple[str, str] | None:
    if not suggested_tools and not suggested_actions:
        return None
    redis = await get_redis()
    validate_token = str(uuid.uuid4())
    action_token = str(uuid.uuid4())
    payload = {
        "owner_user_id": owner_user_id,
        "suggested_tools": suggested_tools[:5],
        "suggested_actions": suggested_actions[:3],
        "topic": topic.value if topic else None,
        "has_brief": has_brief,
        "brief_tools": (brief_tools or [])[:5],
    }
    raw = json.dumps(payload)
    try:
        await redis.set(f"{_ADVICE_VALIDATE_PREFIX}{validate_token}", raw, ex=900)
        await redis.set(f"{_ADVICE_ACTION_PREFIX}{action_token}", raw, ex=900)
    except Exception:
        return None
    return validate_token, action_token


async def _build_advice_keyboard(
    owner_user_id: int,
    *,
    suggested_tools: list[dict],
    suggested_actions: list[dict],
    topic: AdviceTopic | None = None,
    has_brief: bool = False,
    brief_tools: list[str] | None = None,
) -> InlineKeyboardMarkup:
    stored = await _store_advice_bundle(
        owner_user_id,
        suggested_tools=suggested_tools,
        suggested_actions=suggested_actions,
        topic=topic if (topic is not None and topic != AdviceTopic.NONE) else None,
        has_brief=has_brief,
        brief_tools=brief_tools,
    )
    validate_token = ""
    action_token = ""
    if stored is not None:
        validate_token, action_token = stored
    rows: list[list[InlineKeyboardButton]] = []
    if topic is not None:
        rows.append([InlineKeyboardButton(text="🔄 Обновить бриф", callback_data=f"{_ADVICE_BRIEF_REFRESH_PREFIX}{topic.value}")])
    if suggested_tools:
        rows.append([InlineKeyboardButton(text="✅ Проверить данными", callback_data=f"{_ADVICE_VALIDATE_PREFIX}{validate_token}")])
    if suggested_actions:
        rows.append([InlineKeyboardButton(text="🧩 Предложить действия (preview)", callback_data=f"{_ADVICE_ACTION_PREFIX}{action_token}")])
    memo_topic = topic.value if isinstance(topic, AdviceTopic) else AdviceTopic.NONE.value
    rows.append([InlineKeyboardButton(text="📄 Memo (PDF)", callback_data=f"{_ADVICE_MEMO_PREFIX}{memo_topic}")])
    rows.append([InlineKeyboardButton(text="🧠 Советник", callback_data="ui:advisor")])
    rows.append([InlineKeyboardButton(text="🏠 Home", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _plan_from_suggested_action(action: dict, *, source: str = "RULE_PHRASE_PACK") -> PlanIntent | None:
    tool_name = str(action.get("tool") or "")
    if not tool_name:
        return None
    payload = dict(action.get("payload_partial") or {})
    payload["dry_run"] = True
    step = PlanStep(step_id="s1", kind="TOOL", tool_name=tool_name, payload=payload, requires_confirm=True, label=str(action.get("label") or tool_name))
    return PlanIntent(plan_id=str(uuid.uuid4()), source=source, steps=[step], summary=str(action.get("why") or "Advice action preview"), confidence=1.0)


async def _render_advice(
    message: Message,
    *,
    topic: AdviceTopic | None,
    question_text: str,
    advice_payload,
    confidence: float,
    intent_source: str,
    brief: DataBriefResult | None = None,
) -> None:
    sanitized = sanitize_advice_payload(advice_payload)
    topic_value = topic.value if isinstance(topic, AdviceTopic) else AdviceTopic.NONE.value
    synthesized = synthesize_advice(topic=topic_value, question_text=question_text, advice=sanitized, brief=brief)
    advice_for_quality = synthesized.model_copy(update={"confidence": confidence})
    badge = assess_advice_intent(advice_for_quality, QualityContext(intent_source=intent_source, intent_kind="ADVICE", tool_name=None))
    text = format_advice_text(synthesized, format_quality_header(badge), badge.warnings, brief=brief)
    keyboard = await _build_advice_keyboard(
        owner_user_id=message.from_user.id,
        suggested_tools=[tool.model_dump() for tool in synthesized.suggested_tools],
        suggested_actions=[action.model_dump() for action in synthesized.suggested_actions],
        topic=topic if (topic is not None and topic != AdviceTopic.NONE) else None,
        has_brief=brief is not None,
        brief_tools=[str(item.get("tool") or "") for item in (brief.tools_run if brief else [])],
    )
    await _save_last_advice_context(
        message,
        topic=topic,
        question_text=question_text,
        advice_text=text,
        synthesized=synthesized,
    )
    await message.answer(text, reply_markup=keyboard)


async def _send_weekly_pdf(message: Message, actor: ToolActor, tenant: ToolTenant, correlation_id: str) -> None:
    await send_weekly_pdf(
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )


def _compose_action_preview_text(formatted_text: str, tool_name: str, response: ToolResponse) -> str:
    lines = [formatted_text, f"🧾 ACTION: {tool_name} (dry-run)"]
    if response.warnings:
        lines.append("⚠️ Важные предупреждения:")
        for warning in response.warnings[:3]:
            lines.append(f"• {warning.message}")
    return "\n".join(lines)


async def handle_tool_call(message: Message, text: str, *, input_kind: str = "text", prebuilt_intent: dict | None = None) -> None:
    if prebuilt_intent is None and await _handle_existing_wizard(message, text):
        return
    if text.lower().strip() in _PLAN_CANCEL_WORDS:
        active = await get_active_plan(message.chat.id)
        if active is not None:
            await clear_active_plan(message.chat.id)
            await write_audit_event("agent_plan_cancelled", {"chat_id": message.chat.id}, correlation_id=get_correlation_id())
            await render_anchor_panel(message, text="План отменён.")
            return

    settings = get_settings()
    if prebuilt_intent is None:
        intent = route_intent(text)
        intent_source = getattr(intent, "source", "RULE")
        llm_confidence = 1.0
    else:
        intent = route_intent("/noop")
        intent.tool = str(prebuilt_intent.get("tool") or "")
        intent.payload = dict(prebuilt_intent.get("payload") or {})
        intent_source = str(prebuilt_intent.get("source") or "LLM")
        llm_confidence = 1.0
    if intent.tool is None:
        correlation_id = get_correlation_id()
        plan = build_plan_from_text(text, actor=message.from_user, settings=settings)
        if plan is not None:
            for step in plan.steps:
                if step.kind != "TOOL" or step.tool_name not in {"create_coupon", "sis_prices_bump"}:
                    continue
                coerced_plan_step = coerce_action_payload(str(step.tool_name), dict(step.payload or {}))
                if not coerced_plan_step.ok:
                    await _start_wizard(
                        message,
                        tool_name=str(step.tool_name),
                        payload_partial=coerced_plan_step.payload,
                        missing_fields=coerced_plan_step.missing_fields,
                        source=plan.source,
                        correlation_id=correlation_id,
                        plan_context={"plan": plan.model_dump(), "step_id": step.step_id},
                    )
                    return
            await write_audit_event(
                "agent_plan_built",
                {"plan_id": plan.plan_id, "source": plan.source, "steps_count": len(plan.steps), "step1_tool": plan.steps[0].tool_name},
                correlation_id=correlation_id,
            )
            plan_result = await execute_plan_preview(
                plan,
                {
                    "settings": settings,
                    "correlation_id": correlation_id,
                    "message": message,
                    "chat_id": message.chat.id,
                    "actor": ToolActor(owner_user_id=message.from_user.id),
                    "tenant": ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
                    "idempotency_key": str(uuid.uuid4()),
                },
            )
            formatted_text, quality_payload = format_tool_response_with_quality(
                plan_result.response,
                intent_source=plan.source if plan.source == "LLM" else "RULE",
                tool_name=plan.steps[0].tool_name,
            )
            preview_text = f"{formatted_text}\n\n{plan_result.preview_text}"
            markup = None
            if plan_result.confirm_needed and plan_result.confirm_cb_data and plan_result.confirm_only_main_cb_data and plan_result.cancel_cb_data:
                markup = _plan_confirm_markup(plan_result.confirm_cb_data, plan_result.confirm_only_main_cb_data, plan_result.cancel_cb_data)
            await message.answer(preview_text, reply_markup=markup)
            await write_audit_event("quality_assessment", quality_payload, correlation_id=correlation_id)
            await write_audit_event("tool_result_quality", quality_payload, correlation_id=correlation_id)
            return

        lowered_text = text.lower()
        if ("купон" in lowered_text or "скидк" in lowered_text) and ("репрайс" in lowered_text or "обнови цены" in lowered_text or "пересчитай цены" in lowered_text):
            await message.answer("Нельзя безопасно объединить два commit-действия в один план. Выбери отдельно: «Сделать купон» или «Сделать репрайс».")
            return

        topic = classify_advice_topic(text)
        if _looks_like_advice_query(text) and topic != AdviceTopic.NONE:
            playbook = build_playbook(topic, preset_id=topic.value)
            if playbook is not None:
                brief = None
                if _is_data_brief_trigger(text):
                    brief = await _build_data_brief(message, topic, source="text")
                await _render_advice(
                    message,
                    topic=topic if (topic is not None and topic != AdviceTopic.NONE) else None,
                    question_text=text,
                    advice_payload=playbook.advice,
                    confidence=1.0,
                    intent_source="RULE",
                    brief=brief,
                )
                await write_audit_event("advice_playbook_used", {"topic": topic.value, "preset_id": playbook.preset_id}, correlation_id=correlation_id)
                return

        try:
            llm_intent, provider = await llm_plan_intent(text=text, settings=settings, registry=registry)
        except Exception as exc:
            await write_audit_event(
                "llm_intent_failed",
                {
                    "provider": settings.llm_provider,
                    "error_class": exc.__class__.__name__,
                    "correlation_id": correlation_id,
                },
            )
            await message.answer(intent.error_message or "Не понял запрос. /help")
            await write_retrospective_event(
                correlation_id=correlation_id,
                input_kind=input_kind,
                text=text,
                intent_source="LLM",
                llm_confidence=0.0,
                tool_name="none",
                response=ToolResponse.fail(
                    correlation_id=correlation_id,
                    code="INTENT_RESOLUTION_FAILED",
                    message="Intent resolution failed",
                ),
                artifacts=[],
            )
            return

        if llm_intent.intent_kind == "ADVICE":
            advice = llm_intent.advice
            if advice is None:
                await message.answer("Не смог подготовить рекомендации. /help")
                return
            brief = None
            llm_topic = classify_advice_topic(text)
            if llm_topic != AdviceTopic.NONE and _is_data_brief_trigger(text):
                brief = await _build_data_brief(message, llm_topic, source="text")
            await _render_advice(
                message,
                topic=llm_topic,
                question_text=text,
                advice_payload=advice,
                confidence=llm_intent.confidence,
                intent_source="LLM",
                brief=brief,
            )
            sanitized = sanitize_advice_payload(advice)
            badge = assess_advice_intent(
                sanitized.model_copy(update={"confidence": llm_intent.confidence}),
                QualityContext(intent_source="LLM", intent_kind="ADVICE", tool_name=None),
            )
            quality_payload = {
                "intent_source": "LLM",
                "intent_kind": llm_intent.intent_kind,
                "tool_name": None,
                "confidence": badge.confidence,
                "provenance": badge.provenance,
                "warning_count": len(badge.warnings),
                "top_warning_codes": badge.warnings[:3],
                "correlation_id": correlation_id,
            }
            await write_audit_event(
                "llm_intent_planned",
                {
                    "intent_kind": llm_intent.intent_kind,
                    "confidence": llm_intent.confidence,
                    "provider": provider,
                    "correlation_id": correlation_id,
                },
            )
            await write_audit_event("advice_tools_suggested", {"count": len(sanitized.suggested_tools)}, correlation_id=correlation_id)
            await write_audit_event("advice_actions_suggested", {"count": len(sanitized.suggested_actions)}, correlation_id=correlation_id)
            await write_audit_event("quality_assessment", quality_payload, correlation_id=correlation_id)
            await write_audit_event("advice_quality", quality_payload, correlation_id=correlation_id)
            await write_retrospective_event(
                correlation_id=correlation_id,
                input_kind=input_kind,
                text=text,
                intent_source="LLM",
                llm_confidence=llm_intent.confidence,
                tool_name="advice",
                response=ToolResponse.ok(
                    correlation_id=correlation_id,
                    data={"intent_kind": "ADVICE"},
                    provenance=ToolProvenance(sources=["llm:advisor"], window={}),
                ),
                artifacts=[],
            )
            return

        if llm_intent.tool is None:
            if provider != "OFF":
                await write_audit_event(
                    "llm_intent_failed",
                    {
                        "provider": provider,
                        "error_class": "NO_TOOL",
                        "correlation_id": correlation_id,
                    },
                )
            await message.answer(llm_intent.error_message or intent.error_message or "Не понял запрос. /help")
            await write_retrospective_event(
                correlation_id=correlation_id,
                input_kind=input_kind,
                text=text,
                intent_source="LLM",
                llm_confidence=llm_intent.confidence,
                tool_name="none",
                response=ToolResponse.fail(
                    correlation_id=correlation_id,
                    code="NO_TOOL",
                    message="No tool selected",
                ),
                artifacts=[],
            )
            return

        await write_audit_event(
            "llm_intent_planned",
            {
                "tool": llm_intent.tool,
                "intent_kind": llm_intent.intent_kind,
                "confidence": llm_intent.confidence,
                "provider": provider,
                "correlation_id": correlation_id,
            },
        )
        intent_source = "LLM"
        llm_confidence = llm_intent.confidence
        tool_def = registry.get(llm_intent.tool) if llm_intent.tool else None
        if tool_def and tool_def.kind == "action":
            coerced = coerce_action_payload(llm_intent.tool, llm_intent.payload)
            if not coerced.ok:
                await _start_wizard(
                    message,
                    tool_name=llm_intent.tool,
                    payload_partial=coerced.payload,
                    missing_fields=coerced.missing_fields,
                    source="LLM",
                    correlation_id=correlation_id,
                )
                await write_retrospective_event(
                    correlation_id=correlation_id,
                    input_kind=input_kind,
                    text=text,
                    intent_source="LLM",
                    llm_confidence=llm_intent.confidence,
                    tool_name="none",
                    response=ToolResponse.fail(
                        correlation_id=correlation_id,
                        code="MISSING_PARAMETERS",
                        message=coerced.missing_prompt(),
                    ),
                    artifacts=[],
                )
                return
            llm_intent = llm_intent.model_copy(update={"payload": coerced.payload})
            required_caps = required_capabilities_for_tool(llm_intent.tool)
            if required_caps and str(settings.upstream_mode).upper() == "SIS_HTTP":
                caps = await get_sis_capabilities(settings=settings, correlation_id=correlation_id, force_refresh=False)
                unsupported = [key for key in required_caps if capability_support_status(caps, key) is False]
                if unsupported:
                    await message.answer(f"❌ Ошибка: UPSTREAM_NOT_IMPLEMENTED\nSIS capability '{unsupported[0]}' is not implemented.")
                    await write_retrospective_event(
                        correlation_id=correlation_id,
                        input_kind=input_kind,
                        text=text,
                        intent_source="LLM",
                        llm_confidence=llm_intent.confidence,
                        tool_name=llm_intent.tool,
                        response=ToolResponse.fail(
                            correlation_id=correlation_id,
                            code="UPSTREAM_NOT_IMPLEMENTED",
                            message=f"SIS capability '{unsupported[0]}' is not implemented.",
                        ),
                        artifacts=[],
                    )
                    return
            await write_audit_event(
                "agent_action_planned",
                {
                    "tool_name": llm_intent.tool,
                    "confidence": llm_intent.confidence,
                    "source": "LLM",
                    "payload_keys": sorted(list(coerced.payload.keys()))[:8],
                },
                correlation_id=correlation_id,
            )
        intent.tool = llm_intent.tool
        intent.payload = llm_intent.payload
        intent.presentation = llm_intent.presentation
        intent.error_message = llm_intent.error_message

    if intent.tool == "weekly_preset":
        actor = ToolActor(owner_user_id=message.from_user.id)
        tenant = ToolTenant(
            project="OwnerBot",
            shop_id="shop_001",
            currency="EUR",
            timezone="Europe/Berlin",
            locale="ru-RU",
        )
        correlation_id = get_correlation_id()
        await _send_weekly_pdf(message, actor, tenant, correlation_id)
        await write_retrospective_event(
            correlation_id=correlation_id,
            input_kind=input_kind,
            text=text,
            intent_source=intent_source,
            llm_confidence=llm_confidence,
            tool_name="weekly_preset",
            response=ToolResponse.ok(
                correlation_id=correlation_id,
                data={"preset": "weekly_pdf"},
                provenance=ToolProvenance(sources=["ownerbot_demo"], window={"days": 7}),
            ),
            artifacts=["weekly_pdf"],
        )
        return


    redis = await get_redis()
    effective_mode, _runtime_override = await resolve_effective_mode(settings=settings, redis=redis)

    tool = registry.get(intent.tool)
    if tool and tool.kind == "action":
        coerced_action = coerce_action_payload(intent.tool, intent.payload)
        if not coerced_action.ok:
            await _start_wizard(
                message,
                tool_name=intent.tool,
                payload_partial=coerced_action.payload,
                missing_fields=coerced_action.missing_fields,
                source=intent_source,
                correlation_id=get_correlation_id(),
            )
            return
        intent.payload = coerced_action.payload

    if tool is None:
        correlation_id = get_correlation_id()
        response = await run_tool(
            intent.tool,
            intent.payload,
            message=message,
            actor=ToolActor(owner_user_id=message.from_user.id),
            tenant=ToolTenant(
                project="OwnerBot",
                shop_id="shop_001",
                currency="EUR",
                timezone="Europe/Berlin",
                locale="ru-RU",
            ),
            correlation_id=correlation_id,
            registry=registry,
            intent_source=intent_source,
        )
        formatted_text, quality_payload = format_tool_response_with_quality(response, source_tag=source_tag if "source_tag" in locals() else None, intent_source=intent_source, tool_name=intent.tool)
        await message.answer(formatted_text)
        await write_audit_event("quality_assessment", quality_payload, correlation_id=correlation_id)
        await write_audit_event("tool_result_quality", quality_payload, correlation_id=correlation_id)
        await write_retrospective_event(
            correlation_id=correlation_id,
            input_kind=input_kind,
            text=text,
            intent_source=intent_source,
            llm_confidence=llm_confidence,
            tool_name=intent.tool,
            response=response,
            artifacts=[],
        )
        return

    is_action = tool.kind == "action"
    idempotency_key = str(intent.payload.get("idempotency_key") or uuid.uuid4()) if is_action else get_correlation_id()
    correlation_id = get_correlation_id()
    actor = ToolActor(owner_user_id=message.from_user.id)
    tenant = ToolTenant(
        project="OwnerBot",
        shop_id="shop_001",
        currency="EUR",
        timezone="Europe/Berlin",
        locale="ru-RU",
    )

    await write_audit_event("user_message_received", {"text": text, "tool": intent.tool})
    artifacts: list[str] = []

    if intent.presentation and intent.presentation.get("kind") == "weekly_pdf":
        await _send_weekly_pdf(message, actor, tenant, correlation_id)
        await write_retrospective_event(
            correlation_id=correlation_id,
            input_kind=input_kind,
            text=text,
            intent_source=intent_source,
            llm_confidence=llm_confidence,
            tool_name="weekly_preset",
            response=ToolResponse.ok(
                correlation_id=correlation_id,
                data={"preset": "weekly_pdf"},
                provenance=ToolProvenance(sources=["ownerbot_demo"], window={"days": 7}),
            ),
            artifacts=["weekly_pdf"],
        )
        return

    start = time.perf_counter()
    if is_action:
        response = await run_tool(
            intent.tool,
            intent.payload,
            message=message,
            actor=actor,
            tenant=tenant,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            registry=registry,
            intent_source=intent_source,
        )
        source_tag = detect_source_tag(response)
    else:
        selected_mode, _ping_response = await choose_data_mode(
            effective_mode=effective_mode,
            redis=redis,
            correlation_id=correlation_id,
            ping_callable=lambda: SisClient(settings).ping(correlation_id=correlation_id),
        )
        if selected_mode == "SIS_HTTP":
            response = await run_sis_tool(
                tool_name=intent.tool, payload=intent.payload, correlation_id=correlation_id, settings=settings
            )
            if response.status == "error" and response.error and response.error.code == "NOT_IMPLEMENTED":
                response = await run_tool(
                    intent.tool,
                    intent.payload,
                    message=message,
                    actor=actor,
                    tenant=tenant,
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    registry=registry,
                )
                source_tag = "DEMO"
            else:
                source_tag = "SIS(ownerbot/v1)"
        elif selected_mode == "DEMO":
            response = await run_tool(
                intent.tool,
                intent.payload,
                message=message,
                actor=actor,
                tenant=tenant,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                registry=registry,
            )
            source_tag = "DEMO"
        else:
            response = upstream_unavailable(correlation_id)
            source_tag = None

    latency_ms = int((time.perf_counter() - start) * 1000)
    logger.info("tool_call", extra={"tool": intent.tool, "latency_ms": latency_ms, "status": response.status})

    await write_audit_event("tool_called", {"tool": intent.tool})
    await write_audit_event("tool_result", {"tool": intent.tool, "status": response.status})

    if intent.presentation and intent.presentation.get("kind") == "chart_png" and response.status == "ok":
        days = int(intent.payload.get("days", 14))
        title = f"Revenue trend — последние {days} дней"
        await send_revenue_trend_png(
            message=message,
            trend_response=response.data,
            days=days,
            title=title,
            currency=tenant.currency,
            timezone=tenant.timezone,
            source_tag=source_tag if "source_tag" in locals() else None,
        )
        artifacts.append("chart_png")
        await write_audit_event(
            "artifact_generated",
            {"kind": "chart_png", "correlation_id": correlation_id, "tool": intent.tool},
        )

    if is_action and intent.payload.get("dry_run", False):
        if response.status == "error":
            formatted_text, quality_payload = format_tool_response_with_quality(response, source_tag=source_tag if "source_tag" in locals() else None, intent_source=intent_source, tool_name=intent.tool)
            await message.answer(formatted_text)
            await write_audit_event("quality_assessment", quality_payload, correlation_id=correlation_id)
            await write_audit_event("tool_result_quality", quality_payload, correlation_id=correlation_id)
            await write_retrospective_event(
                correlation_id=correlation_id,
                input_kind=input_kind,
                text=text,
                intent_source=intent_source,
                llm_confidence=llm_confidence,
                tool_name=intent.tool,
                response=response,
                artifacts=artifacts,
            )
            return
        if is_noop_preview(response):
            formatted_text, quality_payload = format_tool_response_with_quality(response, source_tag=source_tag if "source_tag" in locals() else None, intent_source=intent_source, tool_name=intent.tool)
            await message.answer(formatted_text)
            await write_audit_event("quality_assessment", quality_payload, correlation_id=correlation_id)
            await write_audit_event("tool_result_quality", quality_payload, correlation_id=correlation_id)
            await write_retrospective_event(
                correlation_id=correlation_id,
                input_kind=input_kind,
                text=text,
                intent_source=intent_source,
                llm_confidence=llm_confidence,
                tool_name=intent.tool,
                response=response,
                artifacts=artifacts,
            )
            return

        payload_commit = dict(intent.payload)
        payload_commit["dry_run"] = False
        confirm_payload = {
            "tool_name": tool.name,
            "payload_commit": payload_commit,
            "owner_user_id": message.from_user.id,
            "idempotency_key": idempotency_key,
            "source": intent_source,
        }
        token = await create_confirm_token(confirm_payload)
        if requires_force_confirm(response):
            force_payload = dict(payload_commit)
            force_payload["force"] = True
            force_token = await create_confirm_token(
                {
                    "tool_name": tool.name,
                    "payload_commit": force_payload,
                    "owner_user_id": message.from_user.id,
                    "idempotency_key": str(uuid.uuid4()),
                }
            )
            markup = confirm_keyboard_with_force(
                f"{CONFIRM_CB_PREFIX}{token}",
                f"{CONFIRM_CB_PREFIX}{force_token}",
                f"{CANCEL_CB_PREFIX}{token}",
            )
        else:
            markup = confirm_keyboard(f"{CONFIRM_CB_PREFIX}{token}", f"{CANCEL_CB_PREFIX}{token}")
        formatted_text, quality_payload = format_tool_response_with_quality(response, source_tag=source_tag if "source_tag" in locals() else None, intent_source=intent_source, tool_name=intent.tool)
        if intent_source == "LLM":
            await write_audit_event(
                "agent_action_previewed",
                {
                    "tool_name": intent.tool,
                    "would_apply": bool((response.data or {}).get("would_apply", True)),
                    "warnings_count": len(response.warnings),
                },
                correlation_id=correlation_id,
            )
        await message.answer(
            _compose_action_preview_text(formatted_text, intent.tool, response),
            reply_markup=markup,
        )
        await write_audit_event("quality_assessment", quality_payload, correlation_id=correlation_id)
        await write_audit_event("tool_result_quality", quality_payload, correlation_id=correlation_id)
        await write_retrospective_event(
            correlation_id=correlation_id,
            input_kind=input_kind,
            text=text,
            intent_source=intent_source,
            llm_confidence=llm_confidence,
            tool_name=intent.tool,
            response=response,
            artifacts=artifacts,
        )
        return

    formatted_text, quality_payload = format_tool_response_with_quality(response, source_tag=source_tag if "source_tag" in locals() else None, intent_source=intent_source, tool_name=intent.tool)
    await message.answer(formatted_text)
    await write_audit_event("quality_assessment", quality_payload, correlation_id=correlation_id)
    await write_audit_event("tool_result_quality", quality_payload, correlation_id=correlation_id)
    await write_retrospective_event(
        correlation_id=correlation_id,
        input_kind=input_kind,
        text=text,
        intent_source=intent_source,
        llm_confidence=llm_confidence,
        tool_name=intent.tool,
        response=response,
        artifacts=artifacts,
    )





def _truncate_text(text: str, limit: int = 500) -> str:
    compact = text.strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _voice_templates_route(transcript: str) -> str | None:
    normalized = transcript.lower()
    if any(token in normalized for token in ["шаблоны цены", "шаблон цены", "цены", "prices"]):
        return "prices"
    if any(token in normalized for token in ["шаблоны товары", "шаблон товары", "товары", "products"]):
        return "products"
    if any(token in normalized for token in ["шаблоны скидки", "шаблон скидки", "скидки", "discounts"]):
        return "discounts"
    if any(token in normalized for token in ["шаблоны", "пресеты", "templates"]):
        return "main"
    return None


async def _handle_voice_templates_shortcut(message: Message, transcript: str) -> bool:
    route = _voice_templates_route(transcript)
    if route is None:
        return False

    if route == "prices":
        text = "Шаблоны → Цены"
        markup = build_templates_prices_keyboard()
    elif route == "products":
        text = "Шаблоны → Товары"
        markup = build_templates_products_keyboard()
    elif route == "discounts":
        text = "Шаблоны → Скидки"
        markup = build_templates_discounts_keyboard()
    else:
        text = "Шаблоны"
        markup = build_templates_main_keyboard()

    await write_audit_event("voice.route", {"selected_path": "templates", "template_menu": route})
    await message.answer(text, reply_markup=markup)
    return True







@router.callback_query(F.data.startswith("advisor:preset:"))
async def advisor_preset(callback_query: CallbackQuery) -> None:
    if callback_query.data is None or callback_query.message is None:
        return
    topic_raw = callback_query.data.replace("advisor:preset:", "", 1)
    try:
        topic = AdviceTopic(topic_raw)
    except ValueError:
        await callback_query.answer("Неизвестный пресет", show_alert=True)
        return
    playbook = build_playbook(topic, preset_id=topic.value)
    if playbook is None:
        await callback_query.answer("Пресет недоступен", show_alert=True)
        return
    brief = await _build_data_brief(callback_query.message, topic, source="preset")
    advice = sanitize_advice_payload(playbook.advice)
    synthesized = synthesize_advice(topic=topic.value, question_text=topic.value, advice=advice, brief=brief)
    badge = assess_advice_intent(synthesized.model_copy(update={"confidence": 1.0}), QualityContext(intent_source="RULE", intent_kind="ADVICE", tool_name=None))
    text = format_advice_text(synthesized, format_quality_header(badge), badge.warnings, brief=brief)
    keyboard = await _build_advice_keyboard(
        owner_user_id=callback_query.from_user.id,
        suggested_tools=[tool.model_dump() for tool in synthesized.suggested_tools],
        suggested_actions=[action.model_dump() for action in synthesized.suggested_actions],
        topic=topic if (topic is not None and topic != AdviceTopic.NONE) else None,
        has_brief=brief is not None,
        brief_tools=[str(item.get("tool") or "") for item in (brief.tools_run if brief else [])],
    )
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    correlation_id = get_correlation_id()
    await write_audit_event("advice_playbook_used", {"topic": topic.value, "preset_id": playbook.preset_id}, correlation_id=correlation_id)
    await write_audit_event("advice_tools_suggested", {"count": len(advice.suggested_tools)}, correlation_id=correlation_id)
    await write_audit_event("advice_actions_suggested", {"count": len(advice.suggested_actions)}, correlation_id=correlation_id)
    await callback_query.answer()

@router.callback_query(F.data == _WIZARD_CANCEL_CB)
async def cancel_action_wizard(callback_query: CallbackQuery) -> None:
    if callback_query.message is None:
        return
    msg = callback_query.message
    await _cancel_wizard(msg, correlation_id=get_correlation_id())
    await callback_query.answer()


@router.callback_query(F.data.startswith(_WIZARD_PRESET_CB))
async def wizard_preset_value(callback_query: CallbackQuery) -> None:
    if callback_query.message is None or callback_query.data is None:
        return
    state = await _get_wizard_state(callback_query.message.chat.id)
    if state is None:
        await callback_query.answer("Контекст устарел. Повтори команду.", show_alert=True)
        return
    value = callback_query.data.replace(_WIZARD_PRESET_CB, "", 1)
    await _handle_existing_wizard(callback_query.message, value)
    await callback_query.answer()

@router.callback_query(F.data.startswith(_ADVICE_BRIEF_REFRESH_PREFIX))
async def refresh_advice_brief(callback_query: CallbackQuery) -> None:
    if callback_query.data is None or callback_query.message is None:
        return
    topic_raw = callback_query.data.replace(_ADVICE_BRIEF_REFRESH_PREFIX, "", 1)
    try:
        topic = AdviceTopic(topic_raw)
    except ValueError:
        await callback_query.answer("Неизвестная тема", show_alert=True)
        return
    playbook = build_playbook(topic, preset_id=topic.value)
    if playbook is None:
        await callback_query.answer("Пресет недоступен", show_alert=True)
        return
    brief = await _build_data_brief(callback_query.message, topic, source="text", force_refresh=True)
    advice = sanitize_advice_payload(playbook.advice)
    synthesized = synthesize_advice(topic=topic.value, question_text=topic.value, advice=advice, brief=brief)
    badge = assess_advice_intent(synthesized.model_copy(update={"confidence": 1.0}), QualityContext(intent_source="RULE", intent_kind="ADVICE", tool_name=None))
    text = format_advice_text(synthesized, format_quality_header(badge), badge.warnings, brief=brief)
    keyboard = await _build_advice_keyboard(
        owner_user_id=callback_query.from_user.id,
        suggested_tools=[tool.model_dump() for tool in synthesized.suggested_tools],
        suggested_actions=[action.model_dump() for action in synthesized.suggested_actions],
        topic=topic if (topic is not None and topic != AdviceTopic.NONE) else None,
        has_brief=brief is not None,
        brief_tools=[str(item.get("tool") or "") for item in (brief.tools_run if brief else [])],
    )
    await _save_last_advice_context(
        callback_query.message,
        topic=topic,
        question_text=topic.value,
        advice_text=text,
        synthesized=synthesized,
    )
    await callback_query.message.edit_text(text, reply_markup=keyboard)
    await callback_query.answer()


@router.callback_query(F.data.startswith(_ADVICE_MEMO_PREFIX))
async def generate_advice_memo(callback_query: CallbackQuery) -> None:
    if callback_query.data is None or callback_query.message is None:
        return
    topic_raw = callback_query.data.replace(_ADVICE_MEMO_PREFIX, "", 1)
    correlation_id = get_correlation_id()
    advice_cache = await load_last_advice(callback_query.message.chat.id)
    if not advice_cache:
        await callback_query.answer("Сначала получи совет/бриф", show_alert=True)
        await write_audit_event("advice_memo_failed", {"reason": "missing_advice_cache", "topic": topic_raw}, correlation_id=correlation_id)
        return

    brief = None
    has_brief = False
    try:
        brief_topic = AdviceTopic(topic_raw)
    except ValueError:
        brief_topic = AdviceTopic.NONE
    if brief_topic != AdviceTopic.NONE:
        brief = await load_cached_brief(callback_query.message.chat.id, brief_topic)
        has_brief = brief is not None

    try:
        topic_value = str(advice_cache.get("topic") or topic_raw or AdviceTopic.NONE.value)
        pdf_bytes = render_decision_memo_pdf(topic=topic_value, brief=brief, advice_cache=advice_cache)
        await callback_query.message.answer_document(
            BufferedInputFile(pdf_bytes, filename=f"decision_memo_{topic_value}.pdf"),
            caption="📄 Decision Memo (PDF)",
        )
    except Exception:
        await callback_query.answer("Не удалось собрать memo", show_alert=True)
        await write_audit_event("advice_memo_failed", {"reason": "render_error", "topic": topic_raw}, correlation_id=correlation_id)
        return

    bullets_count = len(list(advice_cache.get("hypotheses") or [])) + len(_brief_facts_lines_for_audit(brief))
    await write_audit_event(
        "advice_memo_generated",
        {"topic": topic_value, "has_brief": has_brief, "bullets_count": bullets_count},
        correlation_id=correlation_id,
    )
    await callback_query.answer("Memo готов")


def _brief_facts_lines_for_audit(brief: DataBriefResult | None) -> list[str]:
    if brief is None:
        return []
    lines = [item for item in str(brief.summary or "").split("\n") if item.strip()]
    return lines[:10]


@router.callback_query(F.data.startswith(_ADVICE_VALIDATE_PREFIX))
async def run_advice_validation_tools(callback_query: CallbackQuery) -> None:
    if callback_query.data is None:
        return
    token = callback_query.data.replace(_ADVICE_VALIDATE_PREFIX, "", 1)
    redis = await get_redis()
    raw = await redis.get(f"{_ADVICE_VALIDATE_PREFIX}{token}")
    if not raw:
        await callback_query.answer("Рекомендация устарела", show_alert=True)
        return
    data = json.loads(raw)
    if int(data.get("owner_user_id", 0)) != int(callback_query.from_user.id):
        await callback_query.answer("Недоступно", show_alert=True)
        return
    tools = list(data.get("suggested_tools") or [])[:5]
    if data.get("has_brief"):
        await callback_query.message.answer("📌 Бриф уже собран. Нажмите «🔄 Обновить бриф», если нужно перезапустить отчёты.")
        await callback_query.answer()
        return
    brief_tools = {str(item) for item in (data.get("brief_tools") or [])}
    if brief_tools:
        tools = [item for item in tools if str(item.get("tool") or "") not in brief_tools]
    results: list[str] = []
    success_count = 0
    for idx, item in enumerate(tools, start=1):
        tool_name = str(item.get("tool") or "")
        tool_def = registry.get(tool_name)
        if not tool_name or (tool_def and tool_def.kind == "action"):
            continue
        response = await run_tool(
            tool_name,
            dict(item.get("payload") or {}),
            callback_query=callback_query,
            actor=ToolActor(owner_user_id=callback_query.from_user.id),
            tenant=ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
            correlation_id=get_correlation_id(),
            registry=registry,
            intent_source="LLM",
        )
        if response.status == "ok":
            success_count += 1
        formatted_text, _ = format_tool_response_with_quality(response, intent_source="LLM", tool_name=tool_name)
        short = formatted_text.split("\n", 1)[0]
        results.append(f"{idx}. {tool_name}: {short}")
    summary = "🧪 Проверка данными\n\n" + ("\n".join(results) if results else "Нет доступных REPORT-инструментов.")
    await callback_query.message.answer(summary)
    correlation_id = get_correlation_id()
    await write_audit_event(
        "advice_data_validation_run",
        {"tools_count": len(tools), "success_count": success_count},
        correlation_id=correlation_id,
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith(_ADVICE_ACTION_PREFIX))
async def run_advice_action_preview(callback_query: CallbackQuery) -> None:
    if callback_query.data is None:
        return
    token = callback_query.data.replace(_ADVICE_ACTION_PREFIX, "", 1)
    redis = await get_redis()
    raw = await redis.get(f"{_ADVICE_ACTION_PREFIX}{token}")
    if not raw:
        await callback_query.answer("Рекомендация устарела", show_alert=True)
        return
    data = json.loads(raw)
    if int(data.get("owner_user_id", 0)) != int(callback_query.from_user.id):
        await callback_query.answer("Недоступно", show_alert=True)
        return
    action = next(iter(data.get("suggested_actions") or []), None)
    if not action:
        await callback_query.answer("Нет предложенных действий", show_alert=True)
        return
    plan = _plan_from_suggested_action(action)
    if plan is None:
        await callback_query.answer("Не удалось собрать preview", show_alert=True)
        return
    correlation_id = get_correlation_id()
    plan_result = await execute_plan_preview(
        plan,
        {
            "settings": get_settings(),
            "correlation_id": correlation_id,
            "message": callback_query.message,
            "chat_id": callback_query.message.chat.id,
            "actor": ToolActor(owner_user_id=callback_query.from_user.id),
            "tenant": ToolTenant(project="OwnerBot", shop_id="shop_001", currency="EUR", timezone="Europe/Berlin", locale="ru-RU"),
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    formatted_text, _ = format_tool_response_with_quality(plan_result.response, intent_source="RULE", tool_name=plan.steps[0].tool_name)
    preview_text = f"{formatted_text}\n\n{plan_result.preview_text}"
    markup = None
    if plan_result.confirm_needed and plan_result.confirm_cb_data and plan_result.confirm_only_main_cb_data and plan_result.cancel_cb_data:
        markup = _plan_confirm_markup(plan_result.confirm_cb_data, plan_result.confirm_only_main_cb_data, plan_result.cancel_cb_data)
    await callback_query.message.answer(preview_text, reply_markup=markup)
    await callback_query.answer()



@router.message(Command("flag"))
async def handle_flag_command(message: Message) -> None:
    if message.text is None:
        return
    command_text = re.sub(r"^/flag(?:@\w+)?\s*", "", message.text, flags=re.IGNORECASE)
    if not command_text:
        await message.answer("Формат: /flag OB-1003 причина ...")
        return
    await handle_tool_call(message, f"flag {command_text}")


@router.message(F.text)
async def handle_text(message: Message) -> None:
    if message.text is None:
        return
    await handle_tool_call(message, message.text, input_kind="text")


@router.message(F.voice)
@router.message(F.audio)
@router.message(F.document)
async def handle_voice(message: Message) -> None:
    if message.voice is None and message.audio is None and message.document is None:
        return

    settings = get_settings()
    redis_client = await get_redis()

    attachment = message.voice or message.audio or message.document
    if attachment is None:
        return

    if getattr(attachment, "duration", 0) and int(getattr(attachment, "duration", 0)) > settings.asr_max_seconds:
        await message.answer("Слишком длинное аудио. Пришли запись короче.")
        return

    mime_type = getattr(attachment, "mime_type", None)
    if message.document is not None and mime_type and not mime_type.startswith("audio/"):
        return
    file_id = getattr(attachment, "file_id", None)
    if file_id is None:
        await message.answer("Не удалось прочитать аудио. Попробуй ещё раз.")
        return

    file = await message.bot.get_file(file_id)
    file_stream = await message.bot.download_file(file.file_path)
    audio_bytes = await file_stream.read()

    if len(audio_bytes) > settings.asr_max_bytes:
        await message.answer("Слишком тяжёлое аудио. Пришли файл поменьше.")
        return

    if mime_type in {"audio/ogg", "audio/opus"} and settings.asr_convert_voice_ogg_to_wav:
        try:
            audio_bytes = convert_ogg_to_wav(audio_bytes)
        except Exception:
            await message.answer("Не удалось обработать OGG/OPUS. Попробуй другой формат.")
            return

    provider_name = settings.asr_provider
    try:
        provider = get_asr_provider(settings)
        provider_name = getattr(provider, "name", provider_name)
    except Exception:
        pass

    started = time.perf_counter()
    await write_audit_event("voice.asr", {"stage": "started", "provider": provider_name, "bytes": len(audio_bytes)})
    try:
        provider = get_asr_provider(settings)
        provider_name = getattr(provider, "name", provider_name)
        result = await get_or_transcribe(redis_client, provider, audio_bytes)
    except ASRError as exc:
        await write_audit_event(
            "voice.asr",
            {
                "stage": "failed",
                "code": exc.code,
                "provider": provider_name,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        await message.answer("ASR недоступен. Напиши запрос текстом.")
        return
    except Exception:
        await write_audit_event(
            "voice.asr",
            {
                "stage": "failed",
                "code": "ASR_FAILED",
                "provider": provider_name,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        await message.answer("ASR недоступен. Напиши запрос текстом.")
        return

    transcript_short = _truncate_text(result.text)
    await write_audit_event(
        "voice.asr",
        {
            "stage": "finished",
            "provider": provider_name,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "confidence": result.confidence,
            "bytes": len(audio_bytes),
            "duration": int(getattr(attachment, "duration", 0) or 0),
            "text": transcript_short,
        },
    )
    await message.answer(f'🎙️ Распознал: "{_truncate_text(result.text, limit=160)}"')

    if await _handle_voice_templates_shortcut(message, result.text):
        return

    if result.confidence < settings.asr_confidence_threshold:
        await write_audit_event("voice.route", {"selected_path": "none", "reason": "low_confidence"})
        await message.answer(f'Плохое распознавание, повтори/скажи иначе. Текст: "{_truncate_text(result.text, limit=160)}"')
        return

    await write_audit_event("voice.route", {"selected_path": "tool"})
    await handle_tool_call(message, result.text, input_kind="voice")
