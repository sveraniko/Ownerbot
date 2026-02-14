from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_action


class Payload(BaseModel):
    product_ids: list[str] | None = None
    status_from: Literal["ACTIVE", "ARCHIVED"] | None = None
    target_status: Literal["ACTIVE", "ARCHIVED"]
    reason: str | None = "ownerbot_template"
    force: bool = False
    dry_run: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> "Payload":
        if (not self.product_ids) and self.status_from is None:
            raise ValueError("Either product_ids or status_from must be provided")
        return self


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    actor_id = actor.owner_user_id if actor else 0
    request_payload = {
        "actor_tg_id": actor_id,
        "target_status": payload.target_status,
    }
    if payload.product_ids:
        request_payload["product_ids"] = payload.product_ids
    if payload.status_from is not None:
        request_payload["status_from"] = payload.status_from
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
                "summary": "DEMO: products publish simulated",
                "affected_count": len(payload.product_ids or ["all"]) if payload.product_ids else 34,
                "examples": [{"id": "product:101", "before": "ARCHIVED", "after": payload.target_status}],
                "warnings": [],
            },
            provenance=ToolProvenance(sources=["local_demo:sis_products_publish"], filters_hash="demo"),
        )

    endpoint = "/products/publish/preview" if payload.dry_run else "/products/publish/apply"
    return await run_sis_action(path=endpoint, payload=request_payload, correlation_id=correlation_id, settings=settings)
