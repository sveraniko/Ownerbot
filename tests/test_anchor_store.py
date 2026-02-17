from __future__ import annotations

import pytest

from app.bot.ui.anchor_store import clear_anchor_message_id, get_anchor_message_id, set_anchor_message_id
from app.core.redis import get_test_redis


@pytest.mark.asyncio
async def test_anchor_store_roundtrip(monkeypatch) -> None:
    await get_test_redis()

    async def _test_redis():
        return await get_test_redis()

    monkeypatch.setattr("app.bot.ui.anchor_store.get_redis", _test_redis)

    assert await get_anchor_message_id(101) is None

    await set_anchor_message_id(101, 555)
    assert await get_anchor_message_id(101) == 555

    await clear_anchor_message_id(101)
    assert await get_anchor_message_id(101) is None
