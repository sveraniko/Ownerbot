from __future__ import annotations

import inspect
import logging
import re
import time
import uuid
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from pydantic import ValidationError

from app.actions.confirm_flow import create_confirm_token
from app.asr.cache import get_or_transcribe
from app.asr.mock_provider import MockASRProvider
from app.asr.telegram_voice import download_voice_bytes
from app.bot.keyboards.confirm import confirm_keyboard
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.core.db import session_scope
from app.storage.bootstrap import write_audit_event
from app.tools.contracts import ToolActor, ToolRequest, ToolResponse, ToolTenant
from app.tools.providers.sis_gateway import upstream_unavailable
from app.tools.registry_setup import build_registry
from app.tools.verifier import verify_response

router = Router()
logger = logging.getLogger(__name__)
registry = build_registry()


def intent_from_text(text: str) -> tuple[str | None, dict]:
    normalized = text.lower().strip()
    if normalized.startswith("/notify"):
        notify_message = re.sub(r"^/notify(?:@\w+)?\s*", "", text, flags=re.IGNORECASE).strip()
        return "notify_team", {"message": notify_message}

    notify_phrases = ["уведомь команду", "сообщи менеджеру", "пни менеджера"]
    for phrase in notify_phrases:
        index = normalized.find(phrase)
        if index != -1:
            message = text[index + len(phrase) :].strip()
            message = message.lstrip(" -—:\t").strip()
            return "notify_team", {"message": message}
    flag_keywords = ["флаг", "пометь", "отметь", "flag"]
    flag_order_match = re.search(r"\bob-\d+\b", text, flags=re.IGNORECASE)
    if flag_order_match and any(word in normalized for word in flag_keywords):
        reason = ""
        reason_match = re.search(r"\bпричина\b\s*(.+)", text, flags=re.IGNORECASE)
        if reason_match:
            reason = reason_match.group(1).strip()
        else:
            reason = text[flag_order_match.end() :].strip()
            reason = reason.lstrip(" -—:\t").strip()
        payload = {"order_id": flag_order_match.group(0).upper()}
        if reason:
            payload["reason"] = reason
        return "flag_order", payload
    trend_match = re.search(r"(\d{1,2})\s*(?:дней|дня|дн)", normalized)
    if trend_match and any(word in normalized for word in ["выруч", "продаж"]):
        days = int(trend_match.group(1))
        if 1 <= days <= 60:
            return "revenue_trend", {"days": days}
    order_match = re.search(r"\b(?:заказ|order)\s*(ob-\d+)\b", text, flags=re.IGNORECASE)
    if order_match:
        return "order_detail", {"order_id": order_match.group(1).upper()}
    if any(word in normalized for word in ["чаты", "чат", "без ответа", "не отвеч"]):
        return "chats_unanswered", {}
    if any(word in normalized for word in ["kpi", "выруч", "продаж"]):
        payload: dict = {}
        if "вчера" in normalized:
            payload["day"] = (date.today() - timedelta(days=1)).isoformat()
        return "kpi_snapshot", payload
    if any(word in normalized for word in ["заказ", "завис", "неоплач"]):
        payload = {}
        if "завис" in normalized or "неоплач" in normalized:
            payload["status"] = "stuck"
        return "orders_search", payload
    return None, {}


def format_response(response: ToolResponse) -> str:
    if response.status == "error" and response.error:
        return f"Ошибка: {response.error.code}\n{response.error.message}"
    lines = ["Суть:", "Запрос выполнен."]
    if response.data:
        lines.append("\nЦифры:")
        for key, value in response.data.items():
            lines.append(f"• {key}: {value}")
    if response.provenance:
        lines.append("\nProvenance:")
        if response.provenance.sources:
            for source in response.provenance.sources:
                lines.append(f"• {source}")
        else:
            lines.append("• (none)")
    if response.warnings:
        lines.append("\nWarnings:")
        for warning in response.warnings:
            lines.append(f"• {warning.code}: {warning.message}")
    return "\n".join(lines)


async def call_tool_handler(
    tool,
    payload,
    correlation_id: str,
    session,
    actor: ToolActor,
    bot=None,
) -> ToolResponse:
    params = inspect.signature(tool.handler).parameters
    kwargs = {}
    if "actor" in params:
        kwargs["actor"] = actor
    if "bot" in params:
        kwargs["bot"] = bot
    return await tool.handler(payload, correlation_id, session, **kwargs)


async def handle_tool_call(message: Message, text: str) -> None:
    settings = get_settings()
    tool_name, payload_data = intent_from_text(text)
    if tool_name is None:
        await message.answer("Не понял запрос. Попробуй /help.")
        return

    if settings.upstream_mode != "DEMO":
        response = upstream_unavailable(get_correlation_id())
        await message.answer(format_response(response))
        return

    tool = registry.get(tool_name)
    if tool is None:
        response = ToolResponse.error(
            correlation_id=get_correlation_id(),
            code="NOT_IMPLEMENTED",
            message=f"Tool {tool_name} is not registered.",
        )
        await message.answer(format_response(response))
        return

    try:
        payload = tool.payload_model(**payload_data)
    except ValidationError:
        response = ToolResponse.error(
            correlation_id=get_correlation_id(),
            code="MESSAGE_REQUIRED" if tool_name == "notify_team" else "VALIDATION_ERROR",
            message="Нужен текст уведомления." if tool_name == "notify_team" else "Некорректные данные.",
        )
        await message.answer(format_response(response))
        return
    is_action = tool.kind == "action"
    idempotency_key = str(uuid.uuid4()) if is_action else get_correlation_id()
    tool_request = ToolRequest(
        tool=tool.name,
        correlation_id=get_correlation_id(),
        idempotency_key=idempotency_key,
        actor=ToolActor(owner_user_id=message.from_user.id),
        tenant=ToolTenant(
            project="OwnerBot",
            shop_id="shop_001",
            currency="EUR",
            timezone="Europe/Berlin",
            locale="ru-RU",
        ),
        payload=payload.model_dump(),
    )

    await write_audit_event("user_message_received", {"text": text, "tool": tool_name})

    start = time.perf_counter()
    async with session_scope() as session:
        response = await call_tool_handler(
            tool, payload, tool_request.correlation_id, session, tool_request.actor, bot=message.bot
        )
    response = verify_response(response)
    latency_ms = int((time.perf_counter() - start) * 1000)
    logger.info("tool_call", extra={"tool": tool_name, "latency_ms": latency_ms, "status": response.status})

    await write_audit_event("tool_called", {"tool": tool_name})
    await write_audit_event("tool_result", {"tool": tool_name, "status": response.status})

    if is_action and getattr(payload, "dry_run", False):
        if response.status == "error":
            await message.answer(format_response(response))
            return
        payload_commit = payload.model_dump()
        payload_commit["dry_run"] = False
        confirm_payload = {
            "tool_name": tool.name,
            "payload_commit": payload_commit,
            "owner_user_id": message.from_user.id,
            "idempotency_key": idempotency_key,
        }
        token = await create_confirm_token(confirm_payload)
        await message.answer(
            format_response(response),
            reply_markup=confirm_keyboard(f"confirm:{token}", f"cancel:{token}"),
        )
        return

    await message.answer(format_response(response))


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
    await handle_tool_call(message, message.text)


@router.message(F.voice)
async def handle_voice(message: Message) -> None:
    if message.voice is None:
        return
    redis_client = await get_redis()
    audio_bytes = await download_voice_bytes(message.bot, message.voice.file_id)
    provider = MockASRProvider()
    result = await get_or_transcribe(redis_client, provider, audio_bytes)

    await write_audit_event(
        "voice_transcribed",
        {"confidence": result.confidence, "text": result.text},
    )

    settings = get_settings()
    low_conf_key = f"voice_low_conf:{message.from_user.id}"
    if result.confidence < settings.asr_confidence_threshold:
        low_conf = await redis_client.get(low_conf_key)
        if not low_conf:
            await redis_client.set(low_conf_key, "1", ex=300)
            await message.answer("Не расслышал. Повтори голосом или напиши текстом.")
            return
    await handle_tool_call(message, result.text)
