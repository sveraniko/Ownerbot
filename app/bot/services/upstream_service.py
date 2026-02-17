from __future__ import annotations

from dataclasses import dataclass

from app.core.redis import get_redis
from app.core.settings import get_settings
from app.upstream.mode_store import set_runtime_mode
from app.upstream.selector import resolve_effective_mode


@dataclass(frozen=True)
class UpstreamSnapshot:
    configured_mode: str
    effective_mode: str
    runtime_override: str | None
    auto_ping: str = "n/a"


async def get_upstream_snapshot() -> UpstreamSnapshot:
    settings = get_settings()
    effective_mode = settings.upstream_mode
    runtime_mode: str | None = None
    cached_ping = "n/a"

    try:
        redis = await get_redis()
        effective_mode, runtime_mode = await resolve_effective_mode(settings=settings, redis=redis)
        if effective_mode == "AUTO" or runtime_mode == "AUTO":
            cached_ping = "ok" if await redis.get(":auto_ping_ok") == "1" else "unknown"
    except Exception:
        pass

    return UpstreamSnapshot(
        configured_mode=settings.upstream_mode,
        effective_mode=effective_mode,
        runtime_override=runtime_mode,
        auto_ping=cached_ping,
    )


async def set_runtime_override(mode: str) -> None:
    settings = get_settings()
    redis = await get_redis()
    await set_runtime_mode(redis, settings.upstream_redis_key, mode)


async def clear_runtime_override() -> None:
    await set_runtime_override("")
