from __future__ import annotations

import inspect
import time

from pydantic import ValidationError

from app.actions.capabilities import get_sis_capabilities, required_capabilities_for_tool
from app.core.db import session_scope
from app.core.audit import write_audit_event
from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolResponse, ToolTenant
from app.tools.registry_setup import build_registry
from app.tools.verifier import verify_response


def _safe_validation_details(exc: ValidationError) -> dict:
    safe_errors = []
    for err in exc.errors():
        safe_errors.append({"field": ".".join(str(v) for v in err.get("loc", ())), "code": err.get("type")})
    return {"errors": safe_errors}


async def _llm_action_guard(*, tool_name: str, payload_dict: dict, correlation_id: str, registry, intent_source: str | None) -> ToolResponse | None:
    if str(intent_source).upper() != "LLM":
        return None
    tool = registry.get(tool_name)
    if tool is None or tool.kind != "action":
        return None

    settings = get_settings()
    allowed_actions = set(settings.llm_allowed_action_tools)
    if tool_name not in allowed_actions:
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="ACTION_TOOL_NOT_ALLOWED",
            message="Action tool is not allowed for LLM planner.",
        )

    payload_dict["dry_run"] = True

    required = required_capabilities_for_tool(tool_name)
    if required and str(settings.upstream_mode).upper() == "SIS_HTTP":
        capabilities = await get_sis_capabilities(settings=settings, correlation_id=correlation_id, force_refresh=False)
        capability_map = capabilities.get("capabilities") if isinstance(capabilities, dict) else {}
        for key in required:
            cap = capability_map.get(key)
            if isinstance(cap, dict) and cap.get("supported") is False:
                return ToolResponse.fail(
                    correlation_id=correlation_id,
                    code="UPSTREAM_NOT_IMPLEMENTED",
                    message=f"SIS capability '{key}' is not implemented.",
                    details={"tool": tool_name, "capability": key},
                )
    return None


async def run_tool(
    tool_name: str,
    payload_dict: dict,
    *,
    message=None,
    callback_query=None,
    actor: ToolActor,
    tenant: ToolTenant,
    correlation_id: str,
    idempotency_key: str | None = None,
    session_factory=session_scope,
    registry=None,
    intent_source: str | None = None,
) -> ToolResponse:
    start = time.perf_counter()
    await write_audit_event(
        "tool_call_started",
        {
            "tool": tool_name,
            "idempotency_key": idempotency_key,
            "actor_id": actor.owner_user_id,
        },
        correlation_id=correlation_id,
    )

    async def _finish(response: ToolResponse) -> ToolResponse:
        payload = {
            "tool": tool_name,
            "status": response.status,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "warnings_count": len(response.warnings),
        }
        if response.error is not None:
            payload["error_code"] = response.error.code
        await write_audit_event("tool_call_finished", payload, correlation_id=correlation_id)
        return response

    tool_registry = registry or build_registry()
    tool = tool_registry.get(tool_name)
    if tool is None:
        return await _finish(ToolResponse.fail(
            correlation_id=correlation_id,
            code="NOT_IMPLEMENTED",
            message=f"Tool {tool_name} is not registered.",
        ))

    guard_error = await _llm_action_guard(
        tool_name=tool_name,
        payload_dict=payload_dict,
        correlation_id=correlation_id,
        registry=tool_registry,
        intent_source=intent_source,
    )
    if guard_error is not None:
        return await _finish(guard_error)

    try:
        payload = tool.payload_model(**payload_dict)
    except ValidationError as exc:
        return await _finish(ToolResponse.fail(
            correlation_id=correlation_id,
            code="VALIDATION_ERROR",
            message="Некорректные данные.",
            details=_safe_validation_details(exc),
        ))

    bot = None
    if message is not None:
        bot = message.bot
    if callback_query is not None:
        bot = callback_query.bot

    params = inspect.signature(tool.handler).parameters
    kwargs = {}
    if "actor" in params:
        kwargs["actor"] = actor
    if "bot" in params:
        kwargs["bot"] = bot
    if "idempotency_key" in params:
        kwargs["idempotency_key"] = idempotency_key

    async with session_factory() as session:
        response = await tool.handler(payload, correlation_id, session, **kwargs)

    return await _finish(verify_response(response))
