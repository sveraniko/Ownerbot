from __future__ import annotations

from pydantic import BaseModel

from app.core.settings import get_settings
from app.tools.contracts import ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_request


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session, actor=None) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode == "DEMO":
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "status": "ok",
                "base_currency": "USD",
                "shop_currency": "EUR",
                "latest_rate": 0.92,
                "next_reprice_in_hours": 4,
                "would_apply": True,
            },
            provenance=ToolProvenance(sources=["local_demo:sis_fx_status"], window={"endpoint": "/fx/status"}, filters_hash="demo"),
        )
    return await run_sis_request(method="GET", path="/fx/status", payload=None, correlation_id=correlation_id, settings=settings)
