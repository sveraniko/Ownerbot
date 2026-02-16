from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.bot.ui.ui_cleanup import (
    EPHEMERAL_MESSAGE_IDS_KEY,
    LEGEND_MESSAGE_ID_KEY,
    PANEL_MESSAGE_ID_KEY,
    cleanup_ephemerals,
    clear_state_preserving_ui_anchors,
    show_panel,
)


class DummyState:
    def __init__(self, data: dict | None = None) -> None:
        self.data = dict(data or {})

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, data: dict):
        self.data.update(data)

    async def clear(self):
        self.data = {}


class DummyBot:
    def __init__(self, *, fail_edit: bool = False) -> None:
        self.fail_edit = fail_edit
        self.edits: list[tuple[int, int, str]] = []
        self.sends: list[tuple[int, str]] = []
        self.deletes: list[tuple[int, int]] = []

    async def edit_message_text(self, *, chat_id: int, message_id: int, text: str, reply_markup=None):
        if self.fail_edit:
            raise TelegramBadRequest(method="editMessageText", message="edit failed")
        self.edits.append((chat_id, message_id, text))

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None):
        message_id = 1000 + len(self.sends)
        self.sends.append((chat_id, text))
        return SimpleNamespace(message_id=message_id)

    async def delete_message(self, *, chat_id: int, message_id: int):
        self.deletes.append((chat_id, message_id))


class DummyMessage:
    def __init__(self, bot: DummyBot, *, chat_id: int = 7) -> None:
        self.bot = bot
        self.chat = SimpleNamespace(id=chat_id)


@pytest.mark.asyncio
async def test_show_panel_edits_existing_panel() -> None:
    bot = DummyBot()
    message = DummyMessage(bot)
    state = DummyState({PANEL_MESSAGE_ID_KEY: 42})

    panel_id = await show_panel(message, state, "hello")

    assert panel_id == 42
    assert bot.edits == [(7, 42, "hello")]
    assert bot.sends == []


@pytest.mark.asyncio
async def test_show_panel_sends_new_panel_when_edit_fails() -> None:
    bot = DummyBot(fail_edit=True)
    message = DummyMessage(bot)
    state = DummyState({PANEL_MESSAGE_ID_KEY: 42})

    panel_id = await show_panel(message, state, "hello")

    assert panel_id == 1000
    assert bot.sends == [(7, "hello")]
    assert state.data[PANEL_MESSAGE_ID_KEY] == 1000


@pytest.mark.asyncio
async def test_cleanup_ephemerals_deletes_all_and_clears_list() -> None:
    bot = DummyBot()
    state = DummyState({EPHEMERAL_MESSAGE_IDS_KEY: [11, "12", "x"]})

    await cleanup_ephemerals(state, bot, 7)

    assert bot.deletes == [(7, 11), (7, 12)]
    assert state.data[EPHEMERAL_MESSAGE_IDS_KEY] == []


@pytest.mark.asyncio
async def test_clear_state_preserving_ui_anchors() -> None:
    state = DummyState({LEGEND_MESSAGE_ID_KEY: 10, PANEL_MESSAGE_ID_KEY: 20, "foo": "bar"})

    await clear_state_preserving_ui_anchors(state)

    assert state.data == {LEGEND_MESSAGE_ID_KEY: 10, PANEL_MESSAGE_ID_KEY: 20}
