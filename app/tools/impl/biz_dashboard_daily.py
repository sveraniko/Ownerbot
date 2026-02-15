from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.core.redis import get_redis
from app.notify import build_daily_digest, render_revenue_trend_png, render_weekly_pdf
from app.tools.contracts import ToolActor, ToolArtifact, ToolProvenance, ToolResponse

_LOCK_TTL_SECONDS = 300
_COOLDOWN_TTL_SECONDS = 120


class Payload(BaseModel):
    format: str = Field(default="png", pattern="^(text|png|pdf)$")
    tz: str = "Europe/Berlin"
    horizon_days: int = Field(default=1, ge=1, le=1)


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    del payload.horizon_days
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    owner_id = actor.owner_user_id
    redis = await get_redis()
    kind = "daily"
    cooldown_key = f"ownerbot:biz:dash:cooldown:{owner_id}:{kind}"
    lock_key = f"ownerbot:biz:dash:lock:{owner_id}:{kind}"

    cooldown_active = await redis.get(cooldown_key)
    if cooldown_active:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"owner_id": owner_id, "message": "Cooldown active. Try again a bit later."},
            provenance=ToolProvenance(sources=["biz_dashboard_daily"], window={}),
        )

    lock_token = str(uuid.uuid4())
    lock_acquired = await redis.set(lock_key, lock_token, ex=_LOCK_TTL_SECONDS, nx=True)
    if not lock_acquired:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"owner_id": owner_id, "message": "Already generating, try later."},
            provenance=ToolProvenance(sources=["biz_dashboard_daily"], window={}),
        )

    try:
        await redis.set(cooldown_key, "1", ex=_COOLDOWN_TTL_SECONDS)
        bundle = await build_daily_digest(owner_id, session, correlation_id)
        text = bundle.text
        if payload.format == "text":
            return ToolResponse.ok(
                correlation_id=correlation_id,
                data={"owner_id": owner_id, "message": text, "warnings": bundle.warnings},
                provenance=ToolProvenance(sources=["build_daily_digest"], window={}),
            )

        if payload.format == "png":
            image = render_revenue_trend_png(bundle.series, "Daily revenue trend", f"tz={payload.tz}")
            return ToolResponse.ok(
                correlation_id=correlation_id,
                data={"owner_id": owner_id, "message": text, "warnings": bundle.warnings},
                artifacts=[
                    ToolArtifact(
                        type="png",
                        filename="business_dashboard_daily.png",
                        content=image,
                        caption=text,
                    )
                ],
                provenance=ToolProvenance(sources=["build_daily_digest", "render_revenue_trend_png"], window={}),
            )

        pdf = render_weekly_pdf(bundle, report_title="OwnerBot Daily Snapshot")
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"owner_id": owner_id, "message": text, "warnings": bundle.warnings},
            artifacts=[
                ToolArtifact(
                    type="pdf",
                    filename="business_dashboard_daily.pdf",
                    content=pdf,
                    caption="Daily snapshot",
                )
            ],
            provenance=ToolProvenance(sources=["build_daily_digest", "render_weekly_pdf"], window={}),
        )
    finally:
        try:
            current = await redis.get(lock_key)
            if current == lock_token:
                await redis.delete(lock_key)
        except Exception:
            pass
