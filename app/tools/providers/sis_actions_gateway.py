from __future__ import annotations

from typing import Any

from app.actions.capabilities import capability_for_endpoint, capability_support_status, get_sis_capabilities
from app.core.settings import Settings
from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning
from app.upstream.sis_actions_client import SisActionsClient


def _truncate_message(message: str, limit: int = 500) -> str:
    compact = " ".join(message.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"


def _extract_error_message(body: dict[str, Any] | None) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return _truncate_message(message)
        if isinstance(error, str) and error.strip():
            return _truncate_message(error)
        message = body.get("message")
        if isinstance(message, str) and message.strip():
            return _truncate_message(message)
    return "SIS actions request failed."


def _provenance(path: str) -> ToolProvenance:
    return ToolProvenance(
        sources=["sis(ownerbot/v1/actions)"],
        window={"scope": "snapshot", "type": "snapshot", "endpoint": path},
        filters_hash="sis_actions",
    )


def _parse_warnings(raw_warnings: Any) -> list[ToolWarning]:
    warnings: list[ToolWarning] = []
    if not isinstance(raw_warnings, list):
        return warnings
    for item in raw_warnings:
        if isinstance(item, dict):
            code = item.get("code")
            message = item.get("message")
            if isinstance(code, str) and code.strip() and isinstance(message, str) and message.strip():
                warnings.append(ToolWarning(code=code, message=message))
                continue
        if isinstance(item, str) and item.strip():
            warnings.append(ToolWarning(code="SIS_WARNING", message=item))
    return warnings


def _normalize_sis_body(body: dict[str, Any] | None) -> tuple[bool, dict[str, Any], list[ToolWarning], str | None]:
    if not isinstance(body, dict):
        return True, {}, [], None

    if isinstance(body.get("ok"), bool):
        ok = bool(body.get("ok"))
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        warnings = _parse_warnings(body.get("warnings"))
        if isinstance(body.get("correlation_id"), str):
            data.setdefault("correlation_id", body["correlation_id"])
        if isinstance(body.get("request_hash"), str):
            data.setdefault("request_hash", body["request_hash"])
        message = None
        if not ok:
            raw_error = body.get("error")
            if isinstance(raw_error, dict):
                err_msg = raw_error.get("message")
                if isinstance(err_msg, str) and err_msg.strip():
                    message = err_msg
            elif isinstance(raw_error, str) and raw_error.strip():
                message = raw_error
            if message is None:
                message = _extract_error_message(body)
        return ok, data, warnings, message

    warnings = _parse_warnings(body.get("warnings"))
    return True, body, warnings, None


async def run_sis_request(
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    correlation_id: str,
    settings: Settings,
    idempotency_key: str | None = None,
) -> ToolResponse:
    capability_key = capability_for_endpoint(path)
    upstream_mode = getattr(settings, "upstream_mode", "SIS_HTTP")
    sis_base_url = getattr(settings, "sis_base_url", "")
    if capability_key and upstream_mode != "DEMO" and bool(sis_base_url):
        capabilities = await get_sis_capabilities(settings=settings, correlation_id=correlation_id, payload_scope=payload)
        supported = capability_support_status(capabilities, capability_key)
        if supported is False:
            endpoint = path
            return ToolResponse.fail(
                correlation_id=correlation_id,
                code="UPSTREAM_NOT_IMPLEMENTED",
                message=f"SIS does not support action={capability_key} yet. Implement SIS endpoint: {endpoint}",
                details={"capability": capability_key, "endpoint": endpoint},
            )

    client = SisActionsClient(settings)
    normalized_method = method.upper()

    if normalized_method == "GET":
        status_code, body = await client.get_action(path, correlation_id=correlation_id)
    elif normalized_method == "PATCH":
        status_code, body = await client.patch_action(path, payload or {}, correlation_id=correlation_id)
    else:
        status_code, body = await client.post_action(
            path,
            payload or {},
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    if status_code == 0:
        return ToolResponse.fail(correlation_id=correlation_id, code="UPSTREAM_UNAVAILABLE", message="SIS upstream is unavailable.")

    ok, data, warnings, envelope_error = _normalize_sis_body(body)

    if status_code >= 400 or not ok:
        code = "UPSTREAM_UNAVAILABLE"
        if status_code == 409:
            code = "ACTION_CONFLICT"
        elif status_code == 422:
            code = "VALIDATION_ERROR"
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code=code,
            message=_truncate_message(envelope_error or _extract_error_message(body)),
            details={"status_code": status_code, "body": body or {}},
        )

    return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=_provenance(path), warnings=warnings or None)


async def run_sis_action(*, path: str, payload: dict[str, Any], correlation_id: str, settings: Settings) -> ToolResponse:
    return await run_sis_request(method="POST", path=path, payload=payload, correlation_id=correlation_id, settings=settings)
