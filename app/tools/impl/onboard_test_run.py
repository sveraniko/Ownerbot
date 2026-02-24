from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.core.redis import get_redis
from app.notify.service import NotificationSettingsService
from app.onboarding.state import apply_onboard_run_result
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.impl import notify_team, ntf_send_digest_now, sis_actions_capabilities

_LOCK_TTL_SECONDS = 120
_COOLDOWN_TTL_SECONDS = 300


class Payload(BaseModel):
    force_refresh_capabilities: bool = True
    send_digest_now: bool = False
    digest_mode: str = Field(default="dry_run", pattern="^(dry_run|commit)$")
    test_notify_team: bool = True


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None, bot=None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    redis = await get_redis()
    owner_id = actor.owner_user_id
    lock_key = f"ownerbot:onboard:test:lock:{owner_id}"
    cooldown_key = f"ownerbot:onboard:test:cooldown:{owner_id}"
    lock_token = str(uuid.uuid4())

    cooldown_active = await redis.get(cooldown_key)
    if cooldown_active:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"owner_id": owner_id, "message": "Onboard test cooldown active. Try again later."},
            provenance=ToolProvenance(sources=["redis", "onboarding_test_run"], window={"scope": "snapshot", "type": "snapshot"}),
        )

    acquired = await redis.set(lock_key, lock_token, ex=_LOCK_TTL_SECONDS, nx=True)
    if not acquired:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"owner_id": owner_id, "message": "Onboard test already running. Try later."},
            provenance=ToolProvenance(sources=["redis", "onboarding_test_run"], window={"scope": "snapshot", "type": "snapshot"}),
        )

    report: dict[str, object] = {"owner_id": owner_id, "steps": []}
    warnings: list[str] = []
    status = "ok"
    try:
        await redis.set(cooldown_key, "1", ex=_COOLDOWN_TTL_SECONDS)

        if payload.force_refresh_capabilities:
            cap_res = await sis_actions_capabilities.handle(
                sis_actions_capabilities.Payload(force_refresh=True),
                correlation_id,
                session,
                actor=actor,
            )
            report["steps"].append({"name": "capabilities_refresh", "status": cap_res.status})
            if cap_res.status != "ok":
                status = "warn"

        if payload.send_digest_now:
            if payload.digest_mode == "dry_run":
                digest_res = await ntf_send_digest_now.handle(ntf_send_digest_now.Payload(), correlation_id, session, actor=actor)
                report["steps"].append(
                    {
                        "name": "send_digest_now",
                        "status": digest_res.status,
                        "mode": "dry_run",
                        "preview": digest_res.data.get("message") if digest_res.status == "ok" else None,
                    }
                )
            else:
                digest_res = await ntf_send_digest_now.handle(ntf_send_digest_now.Payload(), correlation_id, session, actor=actor)
                report["steps"].append({"name": "send_digest_now", "status": digest_res.status, "mode": "commit"})
            if digest_res.status != "ok":
                status = "warn"

        if payload.test_notify_team:
            notify_res = await notify_team.handle(
                notify_team.Payload(message="Onboarding test ping", dry_run=True, silent=True),
                correlation_id,
                session,
                actor=actor,
                bot=bot,
            )
            report["steps"].append(
                {
                    "name": "notify_team_dry_run",
                    "status": notify_res.status,
                    "recipients": notify_res.data.get("recipients") if notify_res.status == "ok" else [],
                }
            )
            if notify_res.status != "ok":
                warnings.append("notify_team dry_run failed")
                status = "warn"

        row = await NotificationSettingsService.get_or_create(session, owner_id)
        apply_onboard_run_result(
            row,
            status=status,
            summary=f"test run: {len(report['steps'])} steps, warnings={len(warnings)}",
            mark_completed=False,
        )
        await session.commit()

        report["status"] = status
        report["warnings"] = warnings
        report["message"] = f"Onboard test run finished: {status.upper()}"
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data=report,
            provenance=ToolProvenance(sources=["sis_actions_capabilities", "ntf_send_digest_now", "notify_team", "redis"], window={"scope": "snapshot", "type": "snapshot"}),
        )
    finally:
        try:
            current = await redis.get(lock_key)
            if current == lock_token:
                await redis.delete(lock_key)
        except Exception:
            pass
