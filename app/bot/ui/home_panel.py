from __future__ import annotations

from app.core.db import check_db
from app.core.redis import check_redis, get_redis
from app.core.settings import get_settings
from app.upstream.selector import resolve_effective_mode


async def build_home_text() -> str:
    settings = get_settings()
    db_ok = False
    redis_ok = False
    effective_mode = settings.upstream_mode

    try:
        db_ok = await check_db()
    except Exception:
        db_ok = False
    try:
        redis_ok = await check_redis()
    except Exception:
        redis_ok = False

    try:
        redis = await get_redis()
        if await redis.ping():
            effective_mode, _ = await resolve_effective_mode(settings=settings, redis=redis)
    except Exception:
        effective_mode = settings.upstream_mode

    return (
        "🏠 OwnerBot — Домой\n\n"
        f"DB: {'✅' if db_ok else '❌'}  Redis: {'✅' if redis_ok else '❌'}\n"
        f"Owner IDs: {', '.join(str(x) for x in settings.owner_ids) or 'none'}\n"
        f"Upstream: cfg={settings.upstream_mode} / eff={effective_mode}\n"
        f"ASR: {settings.asr_provider} | LLM: {settings.llm_provider}\n"
        f"SIS cfg: {'yes' if bool(settings.sis_base_url) else 'no'}\n\n"
        "Навигация ниже (одно окно). /templates доступно в Systems."
    )
