from __future__ import annotations

from pydantic import BaseModel, Field

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    min_revenue_drop_pct: float | None = Field(default=None, ge=0.0)
    min_orders_drop_pct: float | None = Field(default=None, ge=0.0)
    attempt_interval_minutes: int | None = Field(default=None, ge=1)
    max_silence_days: int | None = Field(default=None, ge=1)
    send_on_ops: bool | None = None
    send_on_fx_failed: bool | None = None
    send_on_errors: bool | None = None


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    settings = await NotificationSettingsService.set_digest_quiet_mode(
        session,
        actor.owner_user_id,
        enabled=True,
        attempt_interval_minutes=payload.attempt_interval_minutes,
        max_silence_days=payload.max_silence_days,
    )
    settings = await NotificationSettingsService.set_digest_quiet_rules(
        session,
        actor.owner_user_id,
        min_revenue_drop_pct=payload.min_revenue_drop_pct,
        min_orders_drop_pct=payload.min_orders_drop_pct,
        send_on_ops=payload.send_on_ops,
        send_on_fx_failed=payload.send_on_fx_failed,
        send_on_errors=payload.send_on_errors,
    )

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "digest_quiet_enabled": bool(settings.digest_quiet_enabled),
            "digest_quiet_attempt_interval_minutes": int(settings.digest_quiet_attempt_interval_minutes),
            "digest_quiet_max_silence_days": int(settings.digest_quiet_max_silence_days),
            "digest_quiet_min_revenue_drop_pct": float(settings.digest_quiet_min_revenue_drop_pct),
            "digest_quiet_min_orders_drop_pct": float(settings.digest_quiet_min_orders_drop_pct),
            "digest_quiet_send_on_ops": bool(settings.digest_quiet_send_on_ops),
            "digest_quiet_send_on_fx_failed": bool(settings.digest_quiet_send_on_fx_failed),
            "digest_quiet_send_on_errors": bool(settings.digest_quiet_send_on_errors),
            "message": "Правила quiet digest обновлены.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings"]),
    )
