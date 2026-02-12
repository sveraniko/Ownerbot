from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_PROCESS_RUNTIME_MODE: str | None = None


async def get_runtime_mode(redis, key: str) -> Optional[str]:
    global _PROCESS_RUNTIME_MODE
    try:
        value = await redis.get(key)
        if value is None:
            return None
        mode = str(value).strip().upper()
        return mode or None
    except Exception:
        logger.warning("runtime_mode_store_read_fallback_memory")
        return _PROCESS_RUNTIME_MODE


async def set_runtime_mode(redis, key: str, mode: str) -> None:
    global _PROCESS_RUNTIME_MODE
    normalized = mode.strip().upper()
    try:
        await redis.set(key, normalized)
        return
    except Exception:
        logger.warning("runtime_mode_store_write_fallback_memory", extra={"mode": normalized})
    _PROCESS_RUNTIME_MODE = normalized
