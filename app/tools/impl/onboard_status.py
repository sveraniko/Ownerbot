from __future__ import annotations

from pydantic import BaseModel

from app.core.settings import get_settings
from app.onboarding.presets import PRESETS
from app.onboarding.service import OnboardContext, build_onboard_checklist
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    pass


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    del payload
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    checklist = await build_onboard_checklist(
        OnboardContext(
            settings=get_settings(),
            session=session,
            owner_id=actor.owner_user_id,
            correlation_id=correlation_id,
        )
    )
    suggestions = [
        {"preset": key, "title": preset.title}
        for key, preset in PRESETS.items()
    ]
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "checklist": checklist,
            "preset_suggestions": suggestions,
            "message": f"Onboarding status: {checklist['status'].upper()}",
        },
        provenance=ToolProvenance(sources=["ownerbot_preflight", "owner_notify_settings", "sis_actions_capabilities"]),
    )
