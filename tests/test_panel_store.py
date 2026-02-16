from __future__ import annotations

import pytest


class _RedisStub:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def set(self, key: str, value: str, ex=None):
        self.data[key] = value

    async def get(self, key: str):
        return self.data.get(key)

    async def delete(self, key: str):
        self.data.pop(key, None)


@pytest.mark.asyncio
async def test_panel_store_home_and_panel_ids(monkeypatch) -> None:
    from app.bot.ui import panel_store

    redis = _RedisStub()

    async def _get_redis():
        return redis

    monkeypatch.setattr(panel_store, "get_redis", _get_redis)

    store = panel_store.PanelStore()
    assert await store.get_home_message_id(1) is None
    assert await store.get_panel_message_id(1) is None

    await store.set_home_message_id(1, 101)
    await store.set_panel_message_id(1, 202)

    assert await store.get_home_message_id(1) == 101
    assert await store.get_panel_message_id(1) == 202

    await store.clear_panel_message_id(1)
    assert await store.get_panel_message_id(1) is None


@pytest.mark.asyncio
async def test_panel_store_transient_add_and_clear(monkeypatch) -> None:
    from app.bot.ui import panel_store

    redis = _RedisStub()

    async def _get_redis():
        return redis

    monkeypatch.setattr(panel_store, "get_redis", _get_redis)

    store = panel_store.PanelStore()
    await store.add_transient_message_id(7, 1)
    await store.add_transient_message_id(7, 2)
    await store.add_transient_message_id(7, 2)

    assert await store.get_transient_message_ids(7) == [1, 2]

    await store.clear_transient_message_ids(7)
    assert await store.get_transient_message_ids(7) == []
