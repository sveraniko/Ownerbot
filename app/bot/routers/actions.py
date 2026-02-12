from __future__ import annotations

import inspect

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.actions.confirm_flow import compute_payload_hash, expire_confirm_token, get_confirm_payload
from app.actions.idempotency import claim_action, finalize_action
from app.bot.routers.owner_console import format_response
from app.core.db import session_scope
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.storage.bootstrap import write_audit_event
from app.tools.contracts import ToolActor, ToolResponse
from app.tools.registry_setup import build_registry
from app.tools.verifier import verify_response

router = Router()
registry = build_registry()


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


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm(callback_query: CallbackQuery) -> None:
    if callback_query.data is None:
        return
    token = callback_query.data.split("confirm:", 1)[1]
    stored = await get_confirm_payload(token)
    if stored is None:
        await callback_query.message.edit_text("Подтверждение истекло. Запусти действие снова.")
        await callback_query.answer()
        return

    payload_hash = stored.get("payload_hash")
    payload = stored.get("payload", {})
    owner_user_id = payload.get("owner_user_id")
    tool_name = payload.get("tool_name")

    expected_hash = compute_payload_hash(payload)
    if payload_hash != expected_hash:
        await write_audit_event(
            "confirm_payload_corrupted",
            {"idempotency_key": payload.get("idempotency_key"), "tool": tool_name},
        )
        await callback_query.message.edit_text("Некорректное подтверждение. Запусти действие снова.")
        await callback_query.answer()
        await expire_confirm_token(token, 10)
        return

    if owner_user_id is None or owner_user_id != callback_query.from_user.id:
        await callback_query.answer("Нет доступа для подтверждения.", show_alert=True)
        return

    payload_commit = payload.get("payload_commit", {})
    idempotency_key = payload.get("idempotency_key")
    if not tool_name or not idempotency_key:
        await callback_query.message.edit_text("Некорректный payload подтверждения.")
        await callback_query.answer()
        return

    await write_audit_event(
        "action_confirmed",
        {"tool": tool_name, "owner_user_id": owner_user_id, "idempotency_key": idempotency_key},
    )

    tool = registry.get(tool_name)
    if tool is None:
        await callback_query.message.edit_text(f"Tool {tool_name} не зарегистрирован.")
        await callback_query.answer()
        return

    correlation_id = get_correlation_id()
    actor = ToolActor(owner_user_id=owner_user_id)

    async with session_scope() as session:
        existing, claimed = await claim_action(
            session,
            idempotency_key=idempotency_key,
            tool=tool.name,
            payload_hash=payload_hash or "unknown",
            correlation_id=correlation_id,
        )
        if not claimed:
            if existing is None:
                await callback_query.message.edit_text("Ошибка подтверждения. Запусти действие снова.")
            elif existing.payload_hash != (payload_hash or "unknown"):
                await callback_query.message.edit_text(
                    "IDEMPOTENCY_MISMATCH. Запусти действие снова."
                )
            elif existing.status == "committed":
                await callback_query.message.edit_text("Уже выполнено.")
            elif existing.status == "in_progress":
                await callback_query.message.edit_text("Уже выполняется. Подожди.")
            else:
                await callback_query.message.edit_text(
                    "Предыдущая попытка завершилась ошибкой. Запусти действие снова."
                )
            await callback_query.answer()
            await expire_confirm_token(token, 60)
            return

        try:
            payload_model = tool.payload_model(**payload_commit)
            response = await call_tool_handler(
                tool, payload_model, correlation_id, session, actor, bot=callback_query.bot
            )
            response = verify_response(response)
            status = "committed" if response.status == "ok" else "failed"
        except Exception as exc:
            status = "failed"
            response = ToolResponse.error(
                correlation_id=correlation_id,
                code="ACTION_EXCEPTION",
                message="Ошибка выполнения действия.",
            )
            await write_audit_event(
                "action_exception",
                {
                    "tool": tool_name,
                    "idempotency_key": idempotency_key,
                    "error": type(exc).__name__,
                },
            )
        finally:
            await finalize_action(
                session,
                idempotency_key=idempotency_key,
                status=status,
                correlation_id=correlation_id,
            )

    event_type = "action_committed" if response.status == "ok" else "action_failed"
    await write_audit_event(
        event_type,
        {
            "tool": tool_name,
            "status": response.status,
            "idempotency_key": idempotency_key,
        },
    )

    await callback_query.message.edit_text(format_response(response))
    await callback_query.answer()
    await expire_confirm_token(token, 60)


@router.callback_query(F.data.startswith("cancel:"))
async def handle_cancel(callback_query: CallbackQuery) -> None:
    if callback_query.data is None:
        return
    token = callback_query.data.split("cancel:", 1)[1]
    redis_client = await get_redis()
    await redis_client.delete(f"confirm:{token}")
    await callback_query.message.edit_text("Отменено.")
    await callback_query.answer()
