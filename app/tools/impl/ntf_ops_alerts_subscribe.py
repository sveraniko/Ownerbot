from __future__ import annotations

from pydantic import BaseModel, Field

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    cooldown_hours: int = Field(default=6, ge=1, le=168)
    unanswered_threshold_hours: int = Field(default=2, ge=0, le=168)
    unanswered_min_count: int = Field(default=1, ge=0, le=999)
    stuck_min_count: int = Field(default=1, ge=0, le=999)
    payment_min_count: int = Field(default=1, ge=0, le=999)
    errors_window_hours: int = Field(default=24, ge=1, le=168)
    errors_min_count: int = Field(default=1, ge=0, le=999)
    low_stock_lte: int = Field(default=5, ge=0, le=999)
    low_stock_min_count: int = Field(default=3, ge=0, le=999)
    out_of_stock_min_count: int = Field(default=1, ge=0, le=999)


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    settings = await NotificationSettingsService.set_ops_alerts(
        session,
        actor.owner_user_id,
        enabled=True,
        cooldown_hours=payload.cooldown_hours,
        rules={
            "ops_unanswered_threshold_hours": payload.unanswered_threshold_hours,
            "ops_unanswered_min_count": payload.unanswered_min_count,
            "ops_stuck_orders_min_count": payload.stuck_min_count,
            "ops_payment_issues_min_count": payload.payment_min_count,
            "ops_errors_window_hours": payload.errors_window_hours,
            "ops_errors_min_count": payload.errors_min_count,
            "ops_low_stock_lte": payload.low_stock_lte,
            "ops_low_stock_min_count": payload.low_stock_min_count,
            "ops_out_of_stock_min_count": payload.out_of_stock_min_count,
        },
    )

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "ops_alerts_enabled": settings.ops_alerts_enabled,
            "ops_alerts_cooldown_hours": settings.ops_alerts_cooldown_hours,
            "message": "Ops alerts включены.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings"], window={"scope": "all_time", "type": "snapshot"}),
    )
