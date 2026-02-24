from __future__ import annotations

from pydantic import BaseModel

from app.actions.capabilities import get_sis_capabilities
from app.core.settings import get_settings
from app.tools.contracts import ToolProvenance, ToolResponse


class Payload(BaseModel):
    force_refresh: bool = False


async def handle(payload: Payload, correlation_id: str, session, actor=None) -> ToolResponse:
    settings = get_settings()
    report = await get_sis_capabilities(
        settings=settings,
        correlation_id=correlation_id,
        force_refresh=payload.force_refresh,
    )
    capabilities = report.get("capabilities") if isinstance(report, dict) else {}
    normalized: dict[str, dict[str, object]] = {}
    if isinstance(capabilities, dict):
        for key, value in capabilities.items():
            if not isinstance(value, dict):
                continue
            status = value.get("status")
            if status not in {"supported", "unsupported", "misconfigured", "offline", "unknown"}:
                status = "unknown"
            normalized[key] = {
                "supported": value.get("supported"),
                "status": status,
                "status_code": value.get("status_code"),
                "endpoint": value.get("endpoint"),
            }

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "effective_upstream_mode": settings.upstream_mode,
            "sis_base_url": settings.sis_base_url,
            "checked_at": report.get("checked_at") if isinstance(report, dict) else None,
            "capabilities": normalized,
        },
        provenance=ToolProvenance(
            sources=["sis(ownerbot/v1/actions)"],
            window={"scope": "capabilities", "type": "snapshot", "endpoint": "capabilities_probe"},
            filters_hash="sis_actions_capabilities",
        ),
    )
