from __future__ import annotations

import json

from app.core.redis import get_redis

_HOME_KEY = "ownerbot:ui:home:{chat_id}"
_PANEL_KEY = "ownerbot:ui:panel:{chat_id}"
_TRANSIENT_KEY = "ownerbot:ui:transient:{chat_id}"
_TRANSIENT_TTL_SECONDS = 86400


class PanelStore:
    async def set_home_message_id(self, chat_id: int, message_id: int) -> None:
        redis = await get_redis()
        await redis.set(_HOME_KEY.format(chat_id=chat_id), str(message_id))

    async def get_home_message_id(self, chat_id: int) -> int | None:
        redis = await get_redis()
        raw = await redis.get(_HOME_KEY.format(chat_id=chat_id))
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    async def set_panel_message_id(self, chat_id: int, message_id: int) -> None:
        redis = await get_redis()
        await redis.set(_PANEL_KEY.format(chat_id=chat_id), str(message_id))

    async def get_panel_message_id(self, chat_id: int) -> int | None:
        redis = await get_redis()
        raw = await redis.get(_PANEL_KEY.format(chat_id=chat_id))
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    async def clear_panel_message_id(self, chat_id: int) -> None:
        redis = await get_redis()
        await redis.delete(_PANEL_KEY.format(chat_id=chat_id))

    async def add_transient_message_id(self, chat_id: int, message_id: int) -> None:
        redis = await get_redis()
        key = _TRANSIENT_KEY.format(chat_id=chat_id)
        current = await self.get_transient_message_ids(chat_id)
        if message_id in current:
            return
        current.append(message_id)
        await redis.set(key, json.dumps(current), ex=_TRANSIENT_TTL_SECONDS)

    async def get_transient_message_ids(self, chat_id: int) -> list[int]:
        redis = await get_redis()
        raw = await redis.get(_TRANSIENT_KEY.format(chat_id=chat_id))
        if raw is None:
            return []
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        result: list[int] = []
        for item in data:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    async def clear_transient_message_ids(self, chat_id: int) -> None:
        redis = await get_redis()
        await redis.delete(_TRANSIENT_KEY.format(chat_id=chat_id))
