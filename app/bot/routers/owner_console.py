from __future__ import annotations

import logging
import re
import time
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.actions.confirm_flow import create_confirm_token
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
from app.bot.ui.formatting import detect_source_tag, format_tool_response
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
from app.llm.router import llm_plan_intent
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse, ToolTenant
from app.tools.providers.sis_gateway import run_sis_tool, upstream_unavailable
from app.tools.registry_setup import build_registry
from app.upstream.selector import choose_data_mode, resolve_effective_mode
from app.upstream.sis_client import SisClient

router = Router()
logger = logging.getLogger(__name__)
registry = build_registry()


async def _send_weekly_pdf(message: Message, actor: ToolActor, tenant: ToolTenant, correlation_id: str) -> None:
    await send_weekly_pdf(
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )


async def handle_tool_call(message: Message, text: str, *, input_kind: str = "text") -> None:
    settings = get_settings()
    intent = route_intent(text)
    intent_source = "RULE"
    llm_confidence = 1.0
    if intent.tool is None:
        correlation_id = get_correlation_id()
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
                "confidence": llm_intent.confidence,
                "provider": provider,
                "correlation_id": correlation_id,
            },
        )
        intent_source = "LLM"
        llm_confidence = llm_intent.confidence
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
        )
        await message.answer(format_tool_response(response, source_tag=source_tag if "source_tag" in locals() else None))
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
            await message.answer(format_tool_response(response, source_tag=source_tag if "source_tag" in locals() else None))
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
            await message.answer(format_tool_response(response, source_tag=source_tag if "source_tag" in locals() else None))
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
        await message.answer(
            format_tool_response(response, source_tag=source_tag if "source_tag" in locals() else None),
            reply_markup=markup,
        )
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

    await message.answer(format_tool_response(response, source_tag=source_tag if "source_tag" in locals() else None))
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
