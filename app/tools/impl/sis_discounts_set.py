from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_action


class Payload(BaseModel):
    product_ids: list[str] | None = None
    only_active: bool | None = None
    stock_lte: int | None = Field(default=None, ge=1, le=9999)
    discount_percent: int = Field(..., ge=1, le=95)
    reason: str | None = "ownerbot_template"
    force: bool = False
    dry_run: bool = True


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    actor_id = actor.owner_user_id if actor else 0
    request_payload = {
        "actor_tg_id": actor_id,
        "discount_percent": payload.discount_percent,
    }
    if payload.product_ids:
        request_payload["product_ids"] = payload.product_ids
    if payload.only_active is not None:
        request_payload["only_active"] = payload.only_active
    if payload.stock_lte is not None:
        request_payload["stock_lte"] = payload.stock_lte
    if payload.reason is not None:
        request_payload["reason"] = payload.reason
    if not payload.dry_run:
        request_payload["force"] = payload.force

    settings = get_settings()
    if settings.upstream_mode == "DEMO":
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "status": "preview" if payload.dry_run else "committed",
                "summary": "DEMO: discounts set simulated",
                "affected_count": len(payload.product_ids or ["all"]) if payload.product_ids else 18,
                "examples": [{"id": "product:101", "discount_before": 0, "discount_after": payload.discount_percent}],
                "warnings": [],
            },
            provenance=ToolProvenance(sources=["local_demo:sis_discounts_set"], filters_hash="demo"),
        )

    endpoint = "/discounts/set/preview" if payload.dry_run else "/discounts/set/apply"
    return await run_sis_action(path=endpoint, payload=request_payload, correlation_id=correlation_id, settings=settings)
