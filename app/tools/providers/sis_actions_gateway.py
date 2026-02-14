from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning
from app.upstream.sis_actions_client import SisActionsClient


def _extract_error_message(body: dict[str, Any] | None) -> str:
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str) and message.strip():
            return message
        error = body.get("error")
        if isinstance(error, str) and error.strip():
            return error
    return "SIS actions request failed."


def _provenance(path: str) -> ToolProvenance:
    return ToolProvenance(
        sources=[f"sis:ownerbot/v1/actions{path}"],
        window=None,
        filters_hash="sis_actions",
    )


async def run_sis_action(*, path: str, payload: dict[str, Any], correlation_id: str, settings: Settings) -> ToolResponse:
    client = SisActionsClient(settings)
    status_code, body = await client.post_action(path, payload, correlation_id=correlation_id)

    if status_code == 0:
        return ToolResponse.fail(correlation_id=correlation_id, code="UPSTREAM_UNAVAILABLE", message="SIS upstream is unavailable.")

    if status_code >= 400:
        code = "UPSTREAM_UNAVAILABLE"
        if status_code == 409:
            code = "ACTION_CONFLICT"
        elif status_code == 422:
            code = "VALIDATION_ERROR"
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code=code,
            message=_extract_error_message(body),
            details={"status_code": status_code, "body": body or {}},
        )

    data = body if isinstance(body, dict) else {}
    warnings: list[ToolWarning] = []
    raw_warnings = data.get("warnings") if isinstance(data, dict) else None
    if isinstance(raw_warnings, list):
        for item in raw_warnings:
            if isinstance(item, dict):
                code = item.get("code")
                message = item.get("message")
                if isinstance(code, str) and code.strip() and isinstance(message, str) and message.strip():
                    warnings.append(ToolWarning(code=code, message=message))
                    continue
            if isinstance(item, str) and item.strip():
                warnings.append(ToolWarning(code="SIS_WARNING", message=item))

    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=_provenance(path), warnings=warnings or None)
