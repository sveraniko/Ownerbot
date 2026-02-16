from __future__ import annotations

import json

from aiogram.filters import Filter
from aiogram.types import Message

from app.core.redis import get_redis

STATE_KEY_PREFIX = "ownerbot:templates:state:"


class TemplateWizardActive(Filter):
    async def __call__(self, message: Message) -> bool | dict[str, dict]:
        if message.text is None:
            return False
        if message.text.startswith("/"):
            return False

        redis = await get_redis()
        raw = await redis.get(f"{STATE_KEY_PREFIX}{message.from_user.id}")
        if not raw:
            return False

        tpl_state = json.loads(raw)
        return {"tpl_state": tpl_state}
