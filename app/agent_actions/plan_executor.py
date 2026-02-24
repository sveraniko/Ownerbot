from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.actions.capabilities import capability_support_status, get_sis_capabilities, required_capabilities_for_tool
from app.actions.confirm_flow import create_confirm_token
from app.bot.services.action_preview import is_noop_preview
from app.bot.services.tool_runner import run_tool
from app.core.contracts import CANCEL_CB_PREFIX, CONFIRM_CB_PREFIX
from app.core.redis import get_redis
from app.core.settings import Settings
from app.core.audit import write_audit_event
from app.tools.contracts import ToolActor, ToolTenant, ToolResponse
from app.tools.registry_setup import build_registry
from app.agent_actions.plan_models import PlanIntent

_PLAN_KEY_PREFIX = "ownerbot:plan:"
_PLAN_TTL_SECONDS = 15 * 60


@dataclass
class PlanPreviewResult:
    response: ToolResponse
    preview_text: str
    confirm_needed: bool
    confirm_cb_data: str | None = None
    cancel_cb_data: str | None = None
    would_apply: bool | None = None


@dataclass
class PlanCommitResult:
    summary_text: str
    step2_ran: bool
    response: ToolResponse


async def _plan_key(chat_id: int) -> str:
    return f"{_PLAN_KEY_PREFIX}{chat_id}"


async def get_active_plan(chat_id: int) -> dict[str, Any] | None:
    redis = await get_redis()
    raw = await redis.get(await _plan_key(chat_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def set_active_plan(chat_id: int, state: dict[str, Any]) -> None:
    redis = await get_redis()
    await redis.set(await _plan_key(chat_id), json.dumps(state), ex=_PLAN_TTL_SECONDS)


async def clear_active_plan(chat_id: int) -> None:
    redis = await get_redis()
    await redis.delete(await _plan_key(chat_id))


async def _validate_step1(plan: PlanIntent, settings: Settings, correlation_id: str) -> str | None:
    step1 = plan.steps[0]
    if step1.tool_name is None:
        return "Некорректный план: tool отсутствует"
    if step1.tool_name not in set(settings.llm_allowed_action_tools):
        return "ACTION_TOOL_NOT_ALLOWED"
    required = required_capabilities_for_tool(step1.tool_name)
    if required and str(settings.upstream_mode).upper() == "SIS_HTTP":
        caps = await get_sis_capabilities(settings=settings, correlation_id=correlation_id)
        for key in required:
            supported = capability_support_status(caps, key)
            if supported is False:
                return f"UPSTREAM_NOT_IMPLEMENTED:{key}"
    return None


def _build_preview_text(plan: PlanIntent, response: ToolResponse) -> tuple[str, bool | None, bool]:
    data = response.data or {}
    would_apply = data.get("would_apply") if isinstance(data.get("would_apply"), bool) else None
    confirm_needed = response.status == "ok" and not is_noop_preview(response)
    affected = data.get("affected_count") or data.get("updated_count") or 0
    lines = [f"🧩 План ({len(plan.steps)} шага):"]
    lines.append(f"1) {plan.steps[0].tool_name} (dry-run) -> would_apply={would_apply}, affected={affected}")
    if len(plan.steps) == 2:
        lines.append("2) Notify team (после подтверждения)")
    return "\n".join(lines), would_apply, confirm_needed


async def execute_plan_preview(plan: PlanIntent, ctx: dict[str, Any]) -> PlanPreviewResult:
    settings: Settings = ctx["settings"]
    correlation_id: str = ctx["correlation_id"]
    guard_error = await _validate_step1(plan, settings, correlation_id)
    if guard_error:
        response = ToolResponse.fail(correlation_id=correlation_id, code="PLAN_BLOCKED", message=guard_error)
        return PlanPreviewResult(response=response, preview_text=f"🧩 План отклонён: {guard_error}", confirm_needed=False)

    step1 = plan.steps[0]
    payload = dict(step1.payload or {})
    payload["dry_run"] = True
    response = await run_tool(
        step1.tool_name or "",
        payload,
        message=ctx.get("message"),
        actor=ctx["actor"],
        tenant=ctx["tenant"],
        correlation_id=correlation_id,
        registry=build_registry(),
        intent_source="LLM" if plan.source == "LLM" else "RULE",
    )
    preview_text, would_apply, confirm_needed = _build_preview_text(plan, response)
    confirm_cb_data = None
    cancel_cb_data = None
    token = None
    if confirm_needed:
        payload_commit = dict(payload)
        payload_commit["dry_run"] = False
        token = await create_confirm_token(
            {
                "tool_name": step1.tool_name,
                "payload_commit": payload_commit,
                "owner_user_id": int(ctx["actor"].owner_user_id),
                "idempotency_key": ctx["idempotency_key"],
                "source": plan.source,
                "plan_id": plan.plan_id,
            }
        )
        confirm_cb_data = f"{CONFIRM_CB_PREFIX}{token}"
        cancel_cb_data = f"{CANCEL_CB_PREFIX}{token}"

    await set_active_plan(
        int(ctx["chat_id"]),
        {
            "plan": plan.model_dump(),
            "confirm_token": token,
            "preview": preview_text,
            "correlation_id": correlation_id,
            "actor_id": int(ctx["actor"].owner_user_id),
        },
    )
    await write_audit_event("agent_plan_previewed", {"plan_id": plan.plan_id, "would_apply": bool(would_apply), "confirm_needed": confirm_needed}, correlation_id=correlation_id)
    return PlanPreviewResult(response=response, preview_text=preview_text, confirm_needed=confirm_needed, confirm_cb_data=confirm_cb_data, cancel_cb_data=cancel_cb_data, would_apply=would_apply)


async def commit_plan(plan_id: str, confirm_token: str, ctx: dict[str, Any]) -> PlanCommitResult:
    state = await get_active_plan(int(ctx["chat_id"]))
    correlation_id = ctx["correlation_id"]
    if not state or state.get("plan", {}).get("plan_id") != plan_id:
        failed = ToolResponse.fail(correlation_id=correlation_id, code="PLAN_NOT_FOUND", message="План устарел")
        return PlanCommitResult(summary_text="План устарел. Запусти заново.", step2_ran=False, response=failed)

    response: ToolResponse = ctx["commit_response"]
    step2_ran = False
    summary = "✅ Шаг 1 выполнен."
    plan = PlanIntent.model_validate(state["plan"])
    if len(plan.steps) == 2 and response.status == "ok":
        notify_message = render_notify_message(plan, response)
        notify_response = await run_tool(
            "notify_team",
            {"message": notify_message, "dry_run": False},
            callback_query=ctx.get("callback_query"),
            actor=ToolActor(owner_user_id=ctx["owner_user_id"]),
            tenant=ctx["tenant"],
            correlation_id=correlation_id,
            registry=build_registry(),
        )
        step2_ran = notify_response.status == "ok"
        if step2_ran:
            summary = f"{summary}\n📣 Команда уведомлена."
    await clear_active_plan(int(ctx["chat_id"]))
    await write_audit_event("agent_plan_committed", {"plan_id": plan_id, "result": response.status, "step2_ran": step2_ran}, correlation_id=correlation_id)
    return PlanCommitResult(summary_text=summary, step2_ran=step2_ran, response=response)


def render_notify_message(plan: PlanIntent, response: ToolResponse) -> str:
    data = response.data or {}
    if plan.steps[0].tool_name == "sis_fx_reprice_auto":
        if is_noop_preview(response):
            return "FX без изменений: apply не нужен (small delta / cooldown)."
        affected = data.get("affected_count") or data.get("updated_count") or 0
        rate = data.get("rate") or "n/a"
        delta = data.get("delta_pct") or "n/a"
        return f"FX репрайс применён: затронуто {affected} товаров, курс {rate}, Δ {delta}%"
    if plan.steps[0].tool_name == "create_coupon":
        code = data.get("code") or "AUTO"
        pct = data.get("percent_off") or "?"
        end = data.get("ends_at") or "(без даты)"
        return f"Создан купон {code} на -{pct}% до {end}"
    return "План выполнен."
