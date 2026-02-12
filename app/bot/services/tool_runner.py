from __future__ import annotations

import inspect

from pydantic import ValidationError

from app.core.db import session_scope
from app.tools.contracts import ToolActor, ToolResponse, ToolTenant
from app.tools.registry_setup import build_registry
from app.tools.verifier import verify_response


def _safe_validation_details(exc: ValidationError) -> dict:
    safe_errors = []
    for err in exc.errors():
        safe_errors.append({"field": ".".join(str(v) for v in err.get("loc", ())), "code": err.get("type")})
    return {"errors": safe_errors}


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
) -> ToolResponse:
    tool_registry = registry or build_registry()
    tool = tool_registry.get(tool_name)
    if tool is None:
        return ToolResponse.error(
            correlation_id=correlation_id,
            code="NOT_IMPLEMENTED",
            message=f"Tool {tool_name} is not registered.",
        )

    try:
        payload = tool.payload_model(**payload_dict)
    except ValidationError as exc:
        return ToolResponse.error(
            correlation_id=correlation_id,
            code="VALIDATION_ERROR",
            message="Некорректные данные.",
            details=_safe_validation_details(exc),
        )

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

    async with session_factory() as session:
        response = await tool.handler(payload, correlation_id, session, **kwargs)

    return verify_response(response)
