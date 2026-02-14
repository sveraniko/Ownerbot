from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.settings import get_settings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.providers.sis_actions_gateway import run_sis_request

_ALLOWED_KEYS = {
    "reprice_schedule_mode",
    "reprice_schedule_interval_hours",
    "reprice_schedule_notify_on_success",
    "reprice_schedule_notify_on_failure",
    "min_rate_delta_abs",
    "min_rate_delta_percent",
    "min_apply_cooldown_hours",
    "provider",
}


class Payload(BaseModel):
    dry_run: bool = True
    updates: dict[str, Any] = Field(default_factory=dict)

    @field_validator("updates")
    @classmethod
    def validate_updates(cls, value: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(value.keys()) - _ALLOWED_KEYS)
        if unknown:
            raise ValueError(f"Unsupported settings keys: {', '.join(unknown)}")
        interval = value.get("reprice_schedule_interval_hours")
        if interval is not None and not (1 <= int(interval) <= 168):
            raise ValueError("reprice_schedule_interval_hours must be between 1 and 168")
        cooldown = value.get("min_apply_cooldown_hours")
        if cooldown is not None and not (0 <= int(cooldown) <= 168):
            raise ValueError("min_apply_cooldown_hours must be between 0 and 168")
        return value


def _compute_diff(snapshot: dict[str, Any], updates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    diff: dict[str, dict[str, Any]] = {}
    for key, after in updates.items():
        before = snapshot.get(key)
        if before != after:
            diff[key] = {"before": before, "after": after}
    return diff


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    settings = get_settings()
    actor_id = actor.owner_user_id if actor else 0

    if settings.upstream_mode == "DEMO":
        before = {
            "reprice_schedule_mode": "manual",
            "reprice_schedule_interval_hours": 12,
            "min_rate_delta_percent": 0.5,
        }
        diff = _compute_diff(before, payload.updates)
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "dry_run": payload.dry_run,
                "diff": diff,
                "note": "preview only" if payload.dry_run else "DEMO: settings update simulated",
            },
            provenance=ToolProvenance(sources=["local_demo:sis_fx_settings_update"], window={"endpoint": "/fx/status" if payload.dry_run else "/fx/settings"}, filters_hash="demo"),
        )

    if payload.dry_run:
        status_resp = await run_sis_request(method="GET", path="/fx/status", payload=None, correlation_id=correlation_id, settings=settings)
        if status_resp.status != "ok":
            return status_resp
        diff = _compute_diff(status_resp.data, payload.updates)
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"dry_run": True, "diff": diff, "note": "preview only"},
            provenance=ToolProvenance(sources=["sis(ownerbot/v1/actions)"], window={"endpoint": "/fx/status"}, filters_hash="sis_actions"),
        )

    commit_payload = {"actor_tg_id": actor_id, "updates": payload.updates}
    commit_resp = await run_sis_request(
        method="PATCH",
        path="/fx/settings",
        payload=commit_payload,
        correlation_id=correlation_id,
        settings=settings,
    )
    if commit_resp.status != "ok":
        return commit_resp
    return commit_resp
