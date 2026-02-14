from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_action


class Payload(BaseModel):
    rate_set_id: str = Field(..., min_length=1)
    input_currency: str = Field(..., min_length=3, max_length=8)
    shop_currency: str = Field(..., min_length=3, max_length=8)
    markup_percent: str = "0"
    markup_additive: str = "0"
    rounding_mode: str = "CEIL_INT"
    rounding_step: str | None = None
    anomaly_threshold_pct: str = "25"
    force: bool = False
    dry_run: bool = True


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    actor_id = actor.owner_user_id if actor else 0
    request_payload = {
        "actor_tg_id": actor_id,
        "rate_set_id": payload.rate_set_id,
        "input_currency": payload.input_currency,
        "shop_currency": payload.shop_currency,
        "markup_percent": payload.markup_percent,
        "markup_additive": payload.markup_additive,
        "rounding_mode": payload.rounding_mode,
        "anomaly_threshold_pct": payload.anomaly_threshold_pct,
    }
    if payload.rounding_mode == "CEIL_STEP" and payload.rounding_step:
        request_payload["rounding_step"] = payload.rounding_step
    if not payload.dry_run:
        request_payload["force"] = payload.force

    settings = get_settings()
    if settings.upstream_mode == "DEMO":
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "status": "preview" if payload.dry_run else "committed",
                "summary": "DEMO: FX reprice simulated" if payload.dry_run else "DEMO: no changes applied",
                "affected_count": 20,
                "max_delta_pct": 14.2,
                "anomaly": {"threshold_pct": 25.0, "max_delta_pct": 14.2, "over_threshold_count": 0},
                "examples": [
                    {"id": "product:310", "before": 120.0, "after": 129.0, "delta_pct": 7.5},
                    {"id": "variant:311", "before": 79.0, "after": 85.0, "delta_pct": 7.6},
                    {"id": "variant:312", "before": 42.0, "after": 46.0, "delta_pct": 9.5},
                ],
            },
            provenance=ToolProvenance(sources=["local_demo:sis_fx_reprice"], filters_hash="demo"),
        )

    endpoint = "/reprice/preview" if payload.dry_run else "/reprice/apply"
    return await run_sis_action(path=endpoint, payload=request_payload, correlation_id=correlation_id, settings=settings)
