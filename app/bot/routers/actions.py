from __future__ import annotations

from contextlib import asynccontextmanager

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.actions.confirm_flow import compute_payload_hash, expire_confirm_token, get_confirm_payload
from app.actions.idempotency import claim_action, finalize_action
from app.bot.services.tool_runner import run_tool
from app.bot.ui.formatting import format_tool_response
from app.core.db import session_scope
from app.core.logging import get_correlation_id
from app.core.redis import get_redis
from app.storage.bootstrap import write_audit_event
from app.tools.contracts import ToolActor, ToolResponse, ToolTenant
from app.tools.registry_setup import build_registry

router = Router()
registry = build_registry()


def _reuse_session_factory(session):
    @asynccontextmanager
    async def _scope():
        yield session

    return _scope


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
    tenant = ToolTenant(
        project="OwnerBot",
        shop_id="shop_001",
        currency="EUR",
        timezone="Europe/Berlin",
        locale="ru-RU",
    )

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
            response = await run_tool(
                tool_name,
                payload_commit,
                callback_query=callback_query,
                actor=actor,
                tenant=tenant,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                session_factory=_reuse_session_factory(session),
                registry=registry,
            )
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

    await callback_query.message.edit_text(format_tool_response(response))
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
