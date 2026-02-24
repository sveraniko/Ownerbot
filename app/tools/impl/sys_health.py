from __future__ import annotations

from pydantic import BaseModel

from app.core.settings import get_settings
from app.tools.contracts import ToolProvenance, ToolResponse
from app.upstream.sis_client import SisClient


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    if not settings.sis_base_url:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"status": "degraded", "reason": "SIS_BASE_URL is not configured"},
            provenance=ToolProvenance(sources=["ownerbot_settings"], window={"scope": "snapshot", "type": "snapshot"}),
        )

    ping = await SisClient(settings).ping(correlation_id)
    if ping.status == "ok":
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"status": "ok", "sis_ping": "ok"},
            provenance=ToolProvenance(sources=["sis:/ownerbot/v1/ping"], window={"scope": "snapshot", "type": "snapshot"}),
        )
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "status": "degraded",
            "sis_ping": "error",
            "error_code": ping.error.code if ping.error else "UNKNOWN",
            "error_message": ping.error.message if ping.error else "unknown",
        },
        provenance=ToolProvenance(sources=["sis:/ownerbot/v1/ping"], window={"scope": "snapshot", "type": "snapshot"}),
    )
