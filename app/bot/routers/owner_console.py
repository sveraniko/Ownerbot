from __future__ import annotations

import logging
import re
import time
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.actions.confirm_flow import create_confirm_token
from app.asr.cache import get_or_transcribe
from app.asr.errors import ASRError
from app.asr.factory import get_asr_provider
from app.asr.telegram_voice import download_voice_bytes
from app.bot.keyboards.confirm import confirm_keyboard
from app.bot.services.intent_router import route_intent
from app.bot.services.tool_runner import run_tool
from app.bot.ui.formatting import format_tool_response
from app.core.contracts import CANCEL_CB_PREFIX, CONFIRM_CB_PREFIX
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.core.audit import write_audit_event
from app.tools.contracts import ToolActor, ToolTenant
from app.tools.providers.sis_gateway import upstream_unavailable
from app.tools.registry_setup import build_registry

router = Router()
logger = logging.getLogger(__name__)
registry = build_registry()


async def handle_tool_call(message: Message, text: str) -> None:
    settings = get_settings()
    intent = route_intent(text)
    if intent.tool is None:
        await message.answer(intent.error_message or "Не понял запрос. /help")
        return

    if settings.upstream_mode != "DEMO":
        response = upstream_unavailable(get_correlation_id())
        await message.answer(format_tool_response(response))
        return

    tool = registry.get(intent.tool)
    if tool is None:
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
            correlation_id=get_correlation_id(),
            registry=registry,
        )
        await message.answer(format_tool_response(response))
        return

    is_action = tool.kind == "action"
    idempotency_key = str(uuid.uuid4()) if is_action else get_correlation_id()
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

    start = time.perf_counter()
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

    latency_ms = int((time.perf_counter() - start) * 1000)
    logger.info("tool_call", extra={"tool": intent.tool, "latency_ms": latency_ms, "status": response.status})

    await write_audit_event("tool_called", {"tool": intent.tool})
    await write_audit_event("tool_result", {"tool": intent.tool, "status": response.status})

    if is_action and intent.payload.get("dry_run", False):
        if response.status == "error":
            await message.answer(format_tool_response(response))
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
        await message.answer(
            format_tool_response(response),
            reply_markup=confirm_keyboard(f"{CONFIRM_CB_PREFIX}{token}", f"{CANCEL_CB_PREFIX}{token}"),
        )
        return

    await message.answer(format_tool_response(response))


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
    settings = get_settings()
    try:
        provider = get_asr_provider(settings)
        result = await get_or_transcribe(redis_client, provider, audio_bytes)
    except ASRError as exc:
        await write_audit_event("asr_failed", {"code": exc.code})
        await message.answer("ASR недоступен. Напиши запрос текстом.")
        return
    except Exception:
        await write_audit_event("asr_failed", {"code": "ASR_FAILED"})
        await message.answer("ASR недоступен. Напиши запрос текстом.")
        return

    await write_audit_event(
        "voice_transcribed",
        {"confidence": result.confidence, "text": result.text},
    )

    low_conf_key = f"voice_low_conf:{message.from_user.id}"
    if result.confidence < settings.asr_confidence_threshold:
        low_conf = await redis_client.get(low_conf_key)
        if not low_conf:
            await redis_client.set(low_conf_key, "1", ex=300)
            await message.answer("Не расслышал. Повтори голосом или напиши текстом.")
            return
    await handle_tool_call(message, result.text)
