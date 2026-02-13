from __future__ import annotations

from pydantic import BaseModel

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_action


class Payload(BaseModel):
    dry_run: bool = True


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    actor_id = actor.owner_user_id if actor else 0
    request_payload = {"actor_tg_id": actor_id}
    settings = get_settings()
    if settings.upstream_mode == "DEMO":
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "status": "preview" if payload.dry_run else "committed",
                "summary": "DEMO: rollback simulated" if payload.dry_run else "DEMO: no changes applied",
                "affected_count": 20,
            },
            provenance=ToolProvenance(sources=["local_demo:sis_fx_rollback"], filters_hash="demo"),
        )

    endpoint = "/reprice/rollback/preview" if payload.dry_run else "/reprice/rollback/apply"
    return await run_sis_action(path=endpoint, payload=request_payload, correlation_id=correlation_id, settings=settings)
