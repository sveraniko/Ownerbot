from __future__ import annotations

import logging
import re
import time
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from app.actions.confirm_flow import create_confirm_token
from app.asr.cache import get_or_transcribe
from app.asr.errors import ASRError
from app.asr.factory import get_asr_provider
from app.asr.telegram_voice import download_voice_bytes
from app.bot.keyboards.confirm import confirm_keyboard, confirm_keyboard_with_force
from app.bot.services.action_force import requires_force_confirm
from app.bot.services.intent_router import route_intent
from app.bot.services.retrospective import write_retrospective_event
from app.bot.services.tool_runner import run_tool
from app.bot.ui.formatting import detect_source_tag, format_tool_response
from app.core.contracts import CANCEL_CB_PREFIX, CONFIRM_CB_PREFIX
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.core.audit import write_audit_event
from app.reports.charts import render_revenue_trend_png
from app.reports.pdf_weekly import build_weekly_report_pdf
from app.llm.router import llm_plan_intent
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse, ToolTenant
from app.tools.providers.sis_gateway import run_sis_tool, upstream_unavailable
from app.tools.registry_setup import build_registry
from app.upstream.selector import choose_data_mode, resolve_effective_mode
from app.upstream.sis_client import SisClient

router = Router()
logger = logging.getLogger(__name__)
registry = build_registry()


def _build_trend_caption(response_data: dict, currency: str) -> str:
    totals = response_data.get("totals", {})
    delta = response_data.get("delta_vs_prev_window") or {}
    total_revenue = float(totals.get("revenue_gross", 0.0))
    delta_pct = delta.get("revenue_gross_pct")
    delta_text = f"{delta_pct}%" if delta_pct is not None else "n/a"
    generated_at = response_data.get("end_day", "n/a")
    return (
        f"Total revenue: {total_revenue:.2f} {currency}\n"
        f"Delta vs prev window: {delta_text}\n"
        f"Currency: {currency}\n"
        f"generated_at: {generated_at}"
    )


async def _send_weekly_pdf(message: Message, actor: ToolActor, tenant: ToolTenant, correlation_id: str) -> None:
    trend_response = await run_tool(
        "revenue_trend",
        {"days": 7},
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )
    kpi_response = await run_tool(
        "kpi_snapshot",
        {},
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )
    stuck_response = await run_tool(
        "orders_search",
        {"status": "stuck", "limit": 10},
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )
    chats_response = await run_tool(
        "chats_unanswered",
        {"limit": 10},
        message=message,
        actor=actor,
        tenant=tenant,
        correlation_id=correlation_id,
        registry=registry,
    )

    if any(resp.status == "error" for resp in [trend_response, kpi_response, stuck_response, chats_response]):
        await message.answer("Не удалось собрать weekly PDF: один из tools вернул ошибку.")
        return

    trend_data = trend_response.data
    kpi_data = kpi_response.data
    stuck_orders = stuck_response.data.get("orders", [])
    chats = chats_response.data.get("threads", [])

    series = trend_data.get("series", [])
    totals = trend_data.get("totals", {})
    daily_revenues = [float(item.get("revenue_gross", 0.0)) for item in series]
    avg_revenue = (sum(daily_revenues) / len(daily_revenues)) if daily_revenues else 0.0
    best_day = max(series, key=lambda x: float(x.get("revenue_gross", 0.0))) if series else None
    worst_day = min(series, key=lambda x: float(x.get("revenue_gross", 0.0))) if series else None

    pdf_payload = {
        "generated_at": trend_response.as_of.isoformat(),
        "correlation_id": correlation_id,
        "kpi_summary": [
            f"day={kpi_data.get('day')}",
            f"revenue_gross={kpi_data.get('revenue_gross')}",
            f"orders_paid={kpi_data.get('orders_paid')}",
            f"aov={kpi_data.get('aov')}",
        ],
        "revenue_summary": [
            f"total={float(totals.get('revenue_gross', 0.0)):.2f} {tenant.currency}",
            f"avg/day={avg_revenue:.2f} {tenant.currency}",
            (
                f"best day={best_day.get('day')} ({float(best_day.get('revenue_gross', 0.0)):.2f} {tenant.currency})"
                if best_day
                else "best day=n/a"
            ),
            (
                f"worst day={worst_day.get('day')} ({float(worst_day.get('revenue_gross', 0.0)):.2f} {tenant.currency})"
                if worst_day
                else "worst day=n/a"
            ),
        ],
        "stuck_orders": [
            f"{item.get('order_id')} | {item.get('status')} | {item.get('amount')} {item.get('currency')}"
            for item in stuck_orders
        ],
        "unanswered_chats": [
            f"{item.get('thread_id')} | customer={item.get('customer_id')} | last={item.get('last_customer_message_at')}"
            for item in chats
        ],
    }

    pdf_bytes = build_weekly_report_pdf(pdf_payload)
    await message.answer_document(
        BufferedInputFile(pdf_bytes, filename="weekly_report_demo.pdf"),
        caption="Weekly PDF report (DEMO)",
    )
    await message.answer(
        "Weekly PDF готов: KPI + trend(7d) + stuck orders + unanswered chats.",
    )
    await write_audit_event(
        "artifact_generated",
        {"kind": "weekly_pdf", "correlation_id": correlation_id, "tool": "weekly_preset"},
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
        png_bytes = render_revenue_trend_png(
            series=response.data.get("series", []),
            currency=tenant.currency,
            title=title,
            tz=tenant.timezone,
        )
        await message.answer_photo(
            BufferedInputFile(png_bytes, filename=f"revenue_trend_{days}d.png"),
            caption=f"Источник: {source_tag or 'DEMO'}\n" + _build_trend_caption(response.data, tenant.currency),
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
async def handle_voice(message: Message) -> None:
    if message.voice is None:
        return
    redis_client = await get_redis()
    audio_bytes = await download_voice_bytes(message.bot, message.voice.file_id)
    settings = get_settings()
    provider_name = settings.asr_provider
    try:
        provider = get_asr_provider(settings)
        provider_name = getattr(provider, "name", provider_name)
    except Exception:
        pass

    started = time.perf_counter()
    await write_audit_event("asr_started", {"provider": provider_name})
    try:
        provider = get_asr_provider(settings)
        provider_name = getattr(provider, "name", provider_name)
        result = await get_or_transcribe(redis_client, provider, audio_bytes)
    except ASRError as exc:
        await write_audit_event(
            "asr_failed",
            {
                "code": exc.code,
                "provider": provider_name,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        await message.answer("ASR недоступен. Напиши запрос текстом.")
        return
    except Exception:
        await write_audit_event(
            "asr_failed",
            {
                "code": "ASR_FAILED",
                "provider": provider_name,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        await message.answer("ASR недоступен. Напиши запрос текстом.")
        return

    await write_audit_event(
        "asr_finished",
        {
            "provider": provider_name,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "confidence": result.confidence,
        },
    )
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
    await handle_tool_call(message, result.text, input_kind="voice")
