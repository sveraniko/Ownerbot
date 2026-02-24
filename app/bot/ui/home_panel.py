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
        "🏠 OwnerBot\n\n"
        f"DB: {'✅' if db_ok else '❌'}  Redis: {'✅' if redis_ok else '❌'}\n"
        f"Владельцы: {', '.join(str(x) for x in settings.owner_ids) or 'нет'}\n"
        f"Источник: настр={settings.upstream_mode} / факт={effective_mode}\n"
        f"SIS: {'да' if bool(settings.sis_base_url) else 'нет'}\n\n"
        "Навигация ниже."
    )
