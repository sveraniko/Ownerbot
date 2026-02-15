from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.capabilities import get_sis_capabilities
from app.core.preflight import preflight_validate_settings
from app.core.redis import get_redis, get_test_redis
from app.core.settings import Settings
from app.notify.service import NotificationSettingsService
from app.upstream.selector import resolve_effective_mode


@dataclass(frozen=True)
class OnboardContext:
    settings: Settings
    session: AsyncSession
    owner_id: int
    correlation_id: str


async def build_onboard_checklist(ctx: OnboardContext) -> dict[str, Any]:
    try:
        redis = await get_redis()
    except RuntimeError:
        redis = await get_test_redis()

    effective_mode, runtime_mode = await resolve_effective_mode(settings=ctx.settings, redis=redis)
    preflight = preflight_validate_settings(ctx.settings, effective_mode=effective_mode, runtime_override=runtime_mode)
    capabilities = await get_sis_capabilities(
        settings=ctx.settings,
        correlation_id=ctx.correlation_id,
        force_refresh=False,
    )
    notify_settings = await NotificationSettingsService.get_or_create(ctx.session, ctx.owner_id)

    items: list[dict[str, str]] = []

    preflight_status = "ok" if preflight.ok else ("warn" if preflight.warnings_count else "fail")
    items.append(
        {
            "key": "sis_connectivity",
            "title": "SIS connectivity",
            "status": preflight_status,
            "details": f"mode={effective_mode}, preflight errors={preflight.errors_count}, warnings={preflight.warnings_count}",
            "fix_hint": "Check SIS_BASE_URL/SIS_OWNERBOT_API_KEY for SIS_HTTP/AUTO modes.",
        }
    )

    sis_http_ready = bool(ctx.settings.sis_base_url and ctx.settings.sis_ownerbot_api_key)
    env_status = "ok" if effective_mode == "DEMO" or sis_http_ready else "warn"
    items.append(
        {
            "key": "upstream_mode",
            "title": "Upstream mode & env",
            "status": env_status,
            "details": (
                f"configured={ctx.settings.upstream_mode}, effective={effective_mode}, "
                f"sis_base_url_present={bool(ctx.settings.sis_base_url)}, sis_api_key_present={bool(ctx.settings.sis_ownerbot_api_key)}"
            ),
            "fix_hint": "For SIS modes, define SIS_BASE_URL and SIS_OWNERBOT_API_KEY.",
        }
    )

    caps = capabilities.get("capabilities") if isinstance(capabilities, dict) else {}
    statuses = [v.get("status") for v in caps.values() if isinstance(v, dict)] if isinstance(caps, dict) else []
    if not statuses:
        caps_status = "warn"
        caps_details = "No capability probe data yet."
    elif any(status in {"misconfigured", "offline"} for status in statuses):
        caps_status = "warn"
        caps_details = f"Capabilities have issues: {', '.join(sorted(set(str(s) for s in statuses)))}"
    elif all(status == "unsupported" for status in statuses):
        caps_status = "fail"
        caps_details = "All SIS action capabilities are unsupported."
    else:
        caps_status = "ok"
        caps_details = f"Capabilities checked: {', '.join(sorted(set(str(s) for s in statuses)))}"

    items.append(
        {
            "key": "capabilities",
            "title": "SIS action capabilities",
            "status": caps_status,
            "details": caps_details,
            "fix_hint": "Open 🧩 SIS actions capabilities and refresh when SIS is reachable.",
        }
    )

    notify_on = any(
        [
            bool(notify_settings.digest_enabled),
            bool(notify_settings.weekly_enabled),
            bool(notify_settings.fx_delta_enabled),
            bool(notify_settings.fx_apply_events_enabled),
            bool(notify_settings.ops_alerts_enabled),
        ]
    )
    notify_status = "ok" if notify_on else "warn"
    items.append(
        {
            "key": "notifications",
            "title": "Notifications config",
            "status": notify_status,
            "details": (
                f"digest={notify_settings.digest_enabled}, weekly={notify_settings.weekly_enabled}, "
                f"ops={notify_settings.ops_alerts_enabled}, fx_delta={notify_settings.fx_delta_enabled}, "
                f"fx_apply={notify_settings.fx_apply_events_enabled}"
            ),
            "fix_hint": "Apply onboarding preset to enable a safe default notification policy.",
        }
    )

    manager_count = len(ctx.settings.manager_chat_ids or [])
    routing_status = "ok" if manager_count else "warn"
    items.append(
        {
            "key": "team_routing",
            "title": "Team routing",
            "status": routing_status,
            "details": f"manager_chat_ids={manager_count}",
            "fix_hint": "Set MANAGER_CHAT_IDS to route notify_team alerts.",
        }
    )

    rank = {"ok": 0, "warn": 1, "fail": 2}
    overall = "ok"
    for item in items:
        if rank[item["status"]] > rank[overall]:
            overall = item["status"]

    return {
        "status": overall,
        "items": items,
        "effective_mode": effective_mode,
        "runtime_mode": runtime_mode,
        "capabilities_checked_at": capabilities.get("checked_at") if isinstance(capabilities, dict) else None,
    }
