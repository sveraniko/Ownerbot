from __future__ import annotations

from pydantic import BaseModel

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_request


class Payload(BaseModel):
    dry_run: bool = True
    force: bool = False
    refresh_snapshot: bool = True


async def handle(
    payload: Payload,
    correlation_id: str,
    session,
    actor: ToolActor | None = None,
    idempotency_key: str | None = None,
) -> ToolResponse:
    actor_id = actor.owner_user_id if actor else 0
    request_payload = {
        "actor_tg_id": actor_id,
        "force_apply": payload.force,
        "refresh_snapshot": payload.refresh_snapshot,
    }
    settings = get_settings()
    if settings.upstream_mode == "DEMO":
        demo_would_apply = True
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "status": "preview" if payload.dry_run else "committed",
                "would_apply": demo_would_apply,
                "affected_count": 8,
                "summary": "DEMO: FX auto reprice simulated",
            },
            provenance=ToolProvenance(sources=["local_demo:sis_fx_reprice_auto"], window={"endpoint": "/fx/preview" if payload.dry_run else "/fx/apply"}, filters_hash="demo"),
        )

    endpoint = "/fx/preview" if payload.dry_run else "/fx/apply"
    return await run_sis_request(
        method="POST",
        path=endpoint,
        payload=request_payload,
        correlation_id=correlation_id,
        settings=settings,
        idempotency_key=idempotency_key if not payload.dry_run else None,
    )
