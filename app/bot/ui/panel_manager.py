from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from app.bot.ui.panel_store import PanelStore


class PanelManager:
    def __init__(self, store: PanelStore | None = None) -> None:
        self._store = store or PanelStore()

    async def ensure_home(self, message: Message, text: str, reply_kb: ReplyKeyboardMarkup) -> int:
        chat_id = message.chat.id
        home_id = await self._store.get_home_message_id(chat_id)
        if home_id is not None:
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=home_id,
                    text=text,
                    reply_markup=reply_kb,
                )
                return home_id
            except TelegramBadRequest:
                await self._safe_delete(chat_id, home_id, bot=message.bot)

        sent = await message.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_kb)
        await self._store.set_home_message_id(chat_id, sent.message_id)
        return sent.message_id

    async def show_panel(
        self,
        message: Message,
        text: str,
        *,
        inline_kb: InlineKeyboardMarkup | None = None,
        mode: str = "replace",
    ) -> int:
        chat_id = message.chat.id
        panel_id = await self._store.get_panel_message_id(chat_id)
        if panel_id is not None:
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=panel_id,
                    text=text,
                    reply_markup=inline_kb,
                )
                return panel_id
            except TelegramBadRequest:
                await self._safe_delete(chat_id, panel_id, bot=message.bot)
                await self._store.clear_panel_message_id(chat_id)

        if mode == "replace":
            await self.clear_transients(chat_id, bot=message.bot)

        sent = await message.bot.send_message(chat_id=chat_id, text=text, reply_markup=inline_kb)
        await self._store.set_panel_message_id(chat_id, sent.message_id)
        return sent.message_id

    async def clear_panel(self, chat_id: int, *, bot) -> None:
        panel_id = await self._store.get_panel_message_id(chat_id)
        if panel_id is None:
            return
        await self._safe_delete(chat_id, panel_id, bot=bot)
        await self._store.clear_panel_message_id(chat_id)

    async def track_transient(self, chat_id: int, message_id: int) -> None:
        await self._store.add_transient_message_id(chat_id, message_id)

    async def clear_transients(self, chat_id: int, *, bot) -> None:
        transient_ids = await self._store.get_transient_message_ids(chat_id)
        for message_id in transient_ids:
            await self._safe_delete(chat_id, message_id, bot=bot)
        await self._store.clear_transient_message_ids(chat_id)

    async def _safe_delete(self, chat_id: int, message_id: int, *, bot) -> None:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest:
            return


_panel_manager = PanelManager()


def get_panel_manager() -> PanelManager:
    return _panel_manager
