from __future__ import annotations

from typing import Optional

from app.core.audit import write_audit_event
from app.core.settings import Settings
from app.tools.contracts import ToolResponse
from app.upstream.mode_store import get_runtime_mode

PING_CACHE_SUFFIX = ":auto_ping_ok"
PING_CACHE_TTL_SEC = 30


async def resolve_effective_mode(*, settings: Settings, redis) -> tuple[str, Optional[str]]:
    runtime_mode = None
    if settings.upstream_runtime_toggle_enabled:
        runtime_mode = await get_runtime_mode(redis, settings.upstream_redis_key)
    if runtime_mode in {"DEMO", "SIS_HTTP", "AUTO"}:
        return runtime_mode, runtime_mode
    return settings.upstream_mode, runtime_mode


async def choose_data_mode(*, effective_mode: str, redis, correlation_id: str, ping_callable) -> tuple[str, Optional[ToolResponse]]:
    if effective_mode == "DEMO":
        return "DEMO", None
    if effective_mode == "SIS_HTTP":
        return "SIS_HTTP", None

    cache_key = f"{PING_CACHE_SUFFIX}"
    cached = None
    try:
        cached = await redis.get(cache_key)
    except Exception:
        cached = None

    if cached == "1":
        return "SIS_HTTP", None

    await write_audit_event("sis_ping_started", {"mode": "AUTO"}, correlation_id=correlation_id)
    ping_resp = await ping_callable()
    await write_audit_event(
        "sis_ping_finished",
        {"mode": "AUTO", "status": ping_resp.status, "error_code": ping_resp.error.code if ping_resp.error else None},
        correlation_id=correlation_id,
    )
    if ping_resp.status == "ok":
        try:
            await redis.set(cache_key, "1", ex=PING_CACHE_TTL_SEC)
        except Exception:
            pass
        return "SIS_HTTP", ping_resp

    await write_audit_event(
        "upstream_unavailable",
        {"mode": "AUTO", "error_class": ping_resp.error.code if ping_resp.error else "UNKNOWN"},
        correlation_id=correlation_id,
    )
    return "DEMO", ping_resp
