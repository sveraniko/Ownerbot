from __future__ import annotations

from pydantic import BaseModel

from app.core.redis import get_redis
from app.core.settings import get_settings
from app.tools.contracts import ToolProvenance, ToolResponse
from app.upstream.selector import resolve_effective_mode


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    settings = get_settings()
    redis = await get_redis()
    effective_mode, runtime_mode = await resolve_effective_mode(settings=settings, redis=redis)
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "upstream_mode": settings.upstream_mode,
            "runtime_mode": runtime_mode,
            "effective_mode": effective_mode,
        },
        provenance=ToolProvenance(sources=["ownerbot_settings", "redis_runtime_toggle"]),
    )
