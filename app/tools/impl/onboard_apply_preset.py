from __future__ import annotations

from pydantic import BaseModel, Field

from app.notify.service import NotificationSettingsService
from app.onboarding.presets import PRESETS, PresetName
from app.onboarding.state import apply_onboard_run_result
from app.storage.models import OwnerNotifySettings
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse


class Payload(BaseModel):
    preset: PresetName
    tz: str | None = None
    dry_run: bool = True


def _current_snapshot(settings: OwnerNotifySettings) -> dict[str, object]:
    return {
        "digest_enabled": bool(settings.digest_enabled),
        "digest_time_local": settings.digest_time_local,
        "digest_tz": settings.digest_tz,
        "digest_format": settings.digest_format,
        "digest_quiet_enabled": bool(settings.digest_quiet_enabled),
        "digest_quiet_attempt_interval_minutes": int(settings.digest_quiet_attempt_interval_minutes),
        "digest_quiet_max_silence_days": int(settings.digest_quiet_max_silence_days),
        "digest_quiet_min_revenue_drop_pct": float(settings.digest_quiet_min_revenue_drop_pct),
        "digest_quiet_min_orders_drop_pct": float(settings.digest_quiet_min_orders_drop_pct),
        "weekly_enabled": bool(settings.weekly_enabled),
        "weekly_day_of_week": int(settings.weekly_day_of_week),
        "weekly_time_local": settings.weekly_time_local,
        "weekly_tz": settings.weekly_tz,
        "ops_alerts_enabled": bool(settings.ops_alerts_enabled),
        "ops_alerts_cooldown_hours": int(settings.ops_alerts_cooldown_hours),
        "ops_unanswered_threshold_hours": int(settings.ops_unanswered_threshold_hours),
        "ops_errors_min_count": int(settings.ops_errors_min_count),
        "fx_delta_enabled": bool(settings.fx_delta_enabled),
        "fx_delta_min_percent": float(settings.fx_delta_min_percent),
        "fx_delta_cooldown_hours": int(settings.fx_delta_cooldown_hours),
        "fx_apply_events_enabled": bool(settings.fx_apply_events_enabled),
        "fx_apply_notify_applied": bool(settings.fx_apply_notify_applied),
        "fx_apply_notify_noop": bool(settings.fx_apply_notify_noop),
        "fx_apply_notify_failed": bool(settings.fx_apply_notify_failed),
        "fx_apply_events_cooldown_hours": int(settings.fx_apply_events_cooldown_hours),
    }


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    preset = PRESETS[payload.preset]
    settings = await NotificationSettingsService.get_or_create(session, actor.owner_user_id)
    before = _current_snapshot(settings)
    target = dict(preset.values)
    if payload.tz:
        target["digest_tz"] = payload.tz
        target["weekly_tz"] = payload.tz

    diffs = []
    for key, after_value in target.items():
        before_value = before.get(key)
        if before_value != after_value:
            diffs.append({"field": key, "before": before_value, "after": after_value})

    if payload.dry_run:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "dry_run": True,
                "preset": preset.name,
                "diffs": diffs,
                "changes_count": len(diffs),
                "note": "Requires confirmation",
                "message": f"Preset {preset.title}: {len(diffs)} planned changes.",
            },
            provenance=ToolProvenance(sources=["owner_notify_settings", "onboarding_presets"]),
        )

    await NotificationSettingsService.set_digest(
        session,
        actor.owner_user_id,
        enabled=bool(target.get("digest_enabled", settings.digest_enabled)),
        time_local=str(target.get("digest_time_local", settings.digest_time_local)),
        tz=str(target.get("digest_tz", settings.digest_tz)),
    )
    await NotificationSettingsService.set_digest_format(
        session,
        actor.owner_user_id,
        digest_format=str(target.get("digest_format", settings.digest_format)),
    )
    await NotificationSettingsService.set_digest_quiet_mode(
        session,
        actor.owner_user_id,
        enabled=bool(target.get("digest_quiet_enabled", settings.digest_quiet_enabled)),
        attempt_interval_minutes=int(target.get("digest_quiet_attempt_interval_minutes", settings.digest_quiet_attempt_interval_minutes)),
        max_silence_days=int(target.get("digest_quiet_max_silence_days", settings.digest_quiet_max_silence_days)),
    )
    await NotificationSettingsService.set_digest_quiet_rules(
        session,
        actor.owner_user_id,
        min_revenue_drop_pct=float(target.get("digest_quiet_min_revenue_drop_pct", settings.digest_quiet_min_revenue_drop_pct)),
        min_orders_drop_pct=float(target.get("digest_quiet_min_orders_drop_pct", settings.digest_quiet_min_orders_drop_pct)),
        send_on_ops=bool(target.get("digest_quiet_send_on_ops", settings.digest_quiet_send_on_ops)),
        send_on_fx_failed=bool(target.get("digest_quiet_send_on_fx_failed", settings.digest_quiet_send_on_fx_failed)),
        send_on_errors=bool(target.get("digest_quiet_send_on_errors", settings.digest_quiet_send_on_errors)),
    )
    await NotificationSettingsService.set_weekly(
        session,
        actor.owner_user_id,
        enabled=bool(target.get("weekly_enabled", settings.weekly_enabled)),
        day_of_week=int(target.get("weekly_day_of_week", settings.weekly_day_of_week)),
        time_local=str(target.get("weekly_time_local", settings.weekly_time_local)),
        tz=str(target.get("weekly_tz", settings.weekly_tz)),
    )
    await NotificationSettingsService.set_ops_alerts(
        session,
        actor.owner_user_id,
        enabled=bool(target.get("ops_alerts_enabled", settings.ops_alerts_enabled)),
        cooldown_hours=int(target.get("ops_alerts_cooldown_hours", settings.ops_alerts_cooldown_hours)),
        rules={
            "ops_unanswered_threshold_hours": int(target.get("ops_unanswered_threshold_hours", settings.ops_unanswered_threshold_hours)),
            "ops_errors_min_count": int(target.get("ops_errors_min_count", settings.ops_errors_min_count)),
        },
    )
    await NotificationSettingsService.set_fx_delta(
        session,
        actor.owner_user_id,
        enabled=bool(target.get("fx_delta_enabled", settings.fx_delta_enabled)),
        min_percent=float(target.get("fx_delta_min_percent", settings.fx_delta_min_percent)),
        cooldown_hours=int(target.get("fx_delta_cooldown_hours", settings.fx_delta_cooldown_hours)),
    )
    await NotificationSettingsService.set_fx_apply_events(
        session,
        actor.owner_user_id,
        enabled=bool(target.get("fx_apply_events_enabled", settings.fx_apply_events_enabled)),
        notify_applied=bool(target.get("fx_apply_notify_applied", settings.fx_apply_notify_applied)),
        notify_noop=bool(target.get("fx_apply_notify_noop", settings.fx_apply_notify_noop)),
        notify_failed=bool(target.get("fx_apply_notify_failed", settings.fx_apply_notify_failed)),
        cooldown_hours=int(target.get("fx_apply_events_cooldown_hours", settings.fx_apply_events_cooldown_hours)),
    )

    row = await NotificationSettingsService.get_or_create(session, actor.owner_user_id)
    apply_onboard_run_result(
        row,
        status="ok",
        summary=f"preset {preset.name} applied ({len(diffs)} changes)",
        mark_completed=True,
    )
    await session.commit()

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "dry_run": False,
            "preset": preset.name,
            "changes_count": len(diffs),
            "diffs": diffs,
            "message": f"Preset {preset.title} applied.",
        },
        provenance=ToolProvenance(sources=["owner_notify_settings", "onboarding_presets"]),
    )
