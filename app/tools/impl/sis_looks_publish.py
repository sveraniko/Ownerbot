from __future__ import annotations

from pydantic import BaseModel, model_validator

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_action


class Payload(BaseModel):
    look_ids: list[str] | None = None
    is_active_from: bool | None = None
    target_active: bool
    reason: str | None = "ownerbot_template"
    force: bool = False
    dry_run: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> "Payload":
        if (not self.look_ids) and self.is_active_from is None:
            raise ValueError("Either look_ids or is_active_from must be provided")
        return self


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    actor_id = actor.owner_user_id if actor else 0
    request_payload = {
        "actor_tg_id": actor_id,
        "target_active": payload.target_active,
    }
    if payload.look_ids:
        request_payload["look_ids"] = payload.look_ids
    if payload.is_active_from is not None:
        request_payload["is_active_from"] = payload.is_active_from
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
                "summary": "DEMO: looks publish simulated",
                "affected_count": len(payload.look_ids or ["all"]) if payload.look_ids else 12,
                "examples": [{"id": "look:501", "before": False, "after": payload.target_active}],
                "warnings": [],
            },
            provenance=ToolProvenance(sources=["local_demo:sis_looks_publish"], filters_hash="demo"),
        )

    endpoint = "/looks/publish/preview" if payload.dry_run else "/looks/publish/apply"
    return await run_sis_action(path=endpoint, payload=request_payload, correlation_id=correlation_id, settings=settings)
