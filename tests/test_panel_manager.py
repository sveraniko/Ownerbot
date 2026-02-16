from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest


class _StoreStub:
    def __init__(self, panel_id: int | None = None) -> None:
        self.panel_id = panel_id
        self.home_id = None
        self.transient_ids: list[int] = []

    async def get_panel_message_id(self, chat_id: int):
        return self.panel_id

    async def set_panel_message_id(self, chat_id: int, message_id: int):
        self.panel_id = message_id

    async def clear_panel_message_id(self, chat_id: int):
        self.panel_id = None

    async def get_home_message_id(self, chat_id: int):
        return self.home_id

    async def set_home_message_id(self, chat_id: int, message_id: int):
        self.home_id = message_id

    async def get_transient_message_ids(self, chat_id: int):
        return list(self.transient_ids)

    async def clear_transient_message_ids(self, chat_id: int):
        self.transient_ids = []

    async def add_transient_message_id(self, chat_id: int, message_id: int):
        self.transient_ids.append(message_id)


class _BotStub:
    def __init__(self, *, edit_raises: bool = False) -> None:
        self.edit_raises = edit_raises
        self.calls: list[tuple] = []

    async def edit_message_text(self, **kwargs):
        self.calls.append(("edit", kwargs))
        if self.edit_raises:
            raise TelegramBadRequest(method="editMessageText", message="message can't be edited")

    async def delete_message(self, **kwargs):
        self.calls.append(("delete", kwargs))

    async def send_message(self, **kwargs):
        self.calls.append(("send", kwargs))
        return SimpleNamespace(message_id=777)


@pytest.mark.asyncio
async def test_panel_manager_show_panel_edits_existing() -> None:
    from app.bot.ui.panel_manager import PanelManager

    store = _StoreStub(panel_id=321)
    bot = _BotStub()
    manager = PanelManager(store=store)
    message = SimpleNamespace(chat=SimpleNamespace(id=10), bot=bot)

    panel_id = await manager.show_panel(message, "hello", mode="replace")

    assert panel_id == 321
    assert bot.calls[0][0] == "edit"
    assert all(call[0] != "send" for call in bot.calls)


@pytest.mark.asyncio
async def test_panel_manager_show_panel_fallbacks_to_send_on_edit_error() -> None:
    from app.bot.ui.panel_manager import PanelManager

    store = _StoreStub(panel_id=321)
    bot = _BotStub(edit_raises=True)
    manager = PanelManager(store=store)
    message = SimpleNamespace(chat=SimpleNamespace(id=10), bot=bot)

    panel_id = await manager.show_panel(message, "hello", mode="replace")

    assert panel_id == 777
    assert store.panel_id == 777
    assert [name for name, _ in bot.calls] == ["edit", "delete", "send"]
