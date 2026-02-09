from __future__ import annotations

import inspect

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.actions.confirm_flow import get_confirm_payload
from app.actions.idempotency import check_idempotency, record_action
from app.bot.routers.owner_console import format_response
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.core.db import session_scope
from app.storage.bootstrap import write_audit_event
from app.tools.contracts import ToolActor, ToolResponse
from app.tools.registry_setup import build_registry
from app.tools.verifier import verify_response

router = Router()
registry = build_registry()


async def call_tool_handler(tool, payload, correlation_id: str, session, actor: ToolActor) -> ToolResponse:
    params = inspect.signature(tool.handler).parameters
    if "actor" in params:
        return await tool.handler(payload, correlation_id, session, actor)
    return await tool.handler(payload, correlation_id, session)


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
    if owner_user_id is None or owner_user_id != callback_query.from_user.id:
        await callback_query.answer("Нет доступа для подтверждения.", show_alert=True)
        return

    tool_name = payload.get("tool_name")
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
        existing = await check_idempotency(session, idempotency_key)
        if existing:
            await callback_query.message.edit_text("Уже выполнено. Повторное выполнение не требуется.")
            await callback_query.answer()
            redis_client = await get_redis()
            await redis_client.delete(f"confirm:{token}")
            return

        payload_model = tool.payload_model(**payload_commit)
        response = await call_tool_handler(tool, payload_model, correlation_id, session, actor)
        response = verify_response(response)

        status = "committed" if response.status == "ok" else "failed"
        await record_action(
            session,
            idempotency_key=idempotency_key,
            tool=tool.name,
            payload_hash=payload_hash or "unknown",
            status=status,
            correlation_id=correlation_id,
        )

    event_type = "action_committed" if response.status == "ok" else "action_failed"
    await write_audit_event(
        event_type,
        {"tool": tool_name, "status": response.status, "idempotency_key": idempotency_key},
    )

    await callback_query.message.edit_text(format_response(response))
    await callback_query.answer()

    redis_client = await get_redis()
    await redis_client.delete(f"confirm:{token}")


@router.callback_query(F.data.startswith("cancel:"))
async def handle_cancel(callback_query: CallbackQuery) -> None:
    if callback_query.data is None:
        return
    token = callback_query.data.split("cancel:", 1)[1]
    redis_client = await get_redis()
    await redis_client.delete(f"confirm:{token}")
    await callback_query.message.edit_text("Отменено.")
    await callback_query.answer()
