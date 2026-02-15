from __future__ import annotations

from pydantic import BaseModel, Field

from app.notify import NotificationSettingsService
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    stage1_after_minutes: int | None = Field(default=None, ge=0)
    repeat_every_minutes: int | None = Field(default=None, ge=0)
    max_repeats: int | None = Field(default=None, ge=0)
    escalation_on_fx_failed: bool | None = None
    escalation_on_out_of_stock: bool | None = None
    escalation_on_stuck_orders_severe: bool | None = None
    escalation_on_errors_spike: bool | None = None
    escalation_on_unanswered_chats_severe: bool | None = None
    escalation_stuck_orders_min: int | None = Field(default=None, ge=0)
    escalation_errors_min: int | None = Field(default=None, ge=0)
    escalation_unanswered_chats_min: int | None = Field(default=None, ge=0)
    escalation_unanswered_threshold_hours: int | None = Field(default=None, ge=1)


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")
    settings = await NotificationSettingsService.set_escalation_rules(
        session,
        actor.owner_user_id,
        stage1_after_minutes=payload.stage1_after_minutes,
        repeat_every_minutes=payload.repeat_every_minutes,
        max_repeats=payload.max_repeats,
        escalation_on_fx_failed=payload.escalation_on_fx_failed,
        escalation_on_out_of_stock=payload.escalation_on_out_of_stock,
        escalation_on_stuck_orders_severe=payload.escalation_on_stuck_orders_severe,
        escalation_on_errors_spike=payload.escalation_on_errors_spike,
        escalation_on_unanswered_chats_severe=payload.escalation_on_unanswered_chats_severe,
        escalation_stuck_orders_min=payload.escalation_stuck_orders_min,
        escalation_errors_min=payload.escalation_errors_min,
        escalation_unanswered_chats_min=payload.escalation_unanswered_chats_min,
        escalation_unanswered_threshold_hours=payload.escalation_unanswered_threshold_hours,
    )
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "owner_id": actor.owner_user_id,
            "escalation_stage1_after_minutes": int(settings.escalation_stage1_after_minutes),
            "escalation_repeat_every_minutes": int(settings.escalation_repeat_every_minutes),
            "escalation_max_repeats": int(settings.escalation_max_repeats),
            "message": "Escalation rules updated.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings"]),
    )
