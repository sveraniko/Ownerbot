from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_action


class Payload(BaseModel):
    bump_percent: str = Field(..., min_length=1)
    bump_additive: str = "0"
    rounding_mode: str = "CEIL_INT"
    dry_run: bool = True


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    actor_id = actor.owner_user_id if actor else 0
    request_payload = {
        "actor_tg_id": actor_id,
        "bump_percent": payload.bump_percent,
        "bump_additive": payload.bump_additive,
        "rounding_mode": payload.rounding_mode,
    }
    settings = get_settings()
    if settings.upstream_mode == "DEMO":
        mode = "preview" if payload.dry_run else "commit"
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "status": "preview" if payload.dry_run else "committed",
                "summary": f"DEMO {mode}: prices bump simulated",
                "affected_count": 12,
                "examples": [
                    {"id": "product:101", "before": 100.0, "after": 110.0, "delta_pct": 10.0},
                    {"id": "variant:201", "before": 49.0, "after": 54.0, "delta_pct": 10.2},
                ],
                "note": "DEMO: no changes applied" if not payload.dry_run else "DEMO preview",
            },
            provenance=ToolProvenance(sources=["local_demo:sis_prices_bump"], filters_hash="demo"),
        )

    endpoint = "/prices/bump/preview" if payload.dry_run else "/prices/bump/apply"
    return await run_sis_action(path=endpoint, payload=request_payload, correlation_id=correlation_id, settings=settings)
