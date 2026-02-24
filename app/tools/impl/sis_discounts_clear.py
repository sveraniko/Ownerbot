from __future__ import annotations

from pydantic import BaseModel

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_action


class Payload(BaseModel):
    product_ids: list[str] | None = None
    only_active: bool | None = None
    clear_compare_at: bool = True
    reason: str | None = "ownerbot_template"
    force: bool = False
    dry_run: bool = True


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    actor_id = actor.owner_user_id if actor else 0
    request_payload = {
        "actor_tg_id": actor_id,
        "clear_compare_at": payload.clear_compare_at,
    }
    if payload.product_ids:
        request_payload["product_ids"] = payload.product_ids
    if payload.only_active is not None:
        request_payload["only_active"] = payload.only_active
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
                "summary": "DEMO: discounts clear simulated",
                "affected_count": len(payload.product_ids or ["all"]) if payload.product_ids else 40,
                "examples": [{"id": "product:101", "discount_before": 15, "discount_after": 0}],
                "warnings": [],
            },
            provenance=ToolProvenance(sources=["local_demo:sis_discounts_clear"], filters_hash="demo", window={"scope": "snapshot", "type": "snapshot"}),
        )

    endpoint = "/discounts/clear/preview" if payload.dry_run else "/discounts/clear/apply"
    return await run_sis_action(path=endpoint, payload=request_payload, correlation_id=correlation_id, settings=settings)
